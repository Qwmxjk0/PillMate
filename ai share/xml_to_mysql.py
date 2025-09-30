#!/usr/bin/env python3
import argparse, zipfile, os, csv, sys, time, tempfile, shutil
from lxml import etree
import pymysql

parser = argparse.ArgumentParser()
parser.add_argument('-z','--zip', required=True)
parser.add_argument('--xml-name', default=None)
parser.add_argument('--db-host', default='127.0.0.1')
parser.add_argument('--db-port', type=int, default=3306)
parser.add_argument('--db-user', default='root')
parser.add_argument('--db-password', default='')
parser.add_argument('--db-name', default='DrugBank')
# NOTE: default out-dir changed to writable /tmp inside container
parser.add_argument('--out-dir', default='/tmp/drugbank_tmp_csv')
parser.add_argument('--drop', action='store_true', help='Drop existing tables before load')
args = parser.parse_args()

os.makedirs(args.out_dir, exist_ok=True)

def extract_xml(zip_path, xml_name=None):
    # extract to a temporary directory (writable) to avoid writing into read-only mount
    tmpdir = tempfile.mkdtemp(prefix="drugbank_xml_")
    try:
        with zipfile.ZipFile(zip_path,'r') as z:
            names = z.namelist()
            target = xml_name if xml_name and xml_name in names else None
            if not target:
                for n in names:
                    if n.lower().endswith('.xml') and 'drugbank' in n.lower():
                        target = n
                        break
            if not target and len(names)==1:
                target = names[0]
            if not target:
                raise SystemExit("XML file not found in zip")
            # extract member into tmpdir by streaming (avoid z.extract to read-only mount)
            with z.open(target) as src, open(os.path.join(tmpdir, os.path.basename(target)), 'wb') as dst:
                shutil.copyfileobj(src, dst)
            return os.path.join(tmpdir, os.path.basename(target))
    except Exception:
        # cleanup on failure
        try:
            shutil.rmtree(tmpdir)
        except Exception:
            pass
        raise

def stream_parse_to_tsv(xml_file, out_dir):
    # ensure out_dir exists (writable path inside container)
    os.makedirs(out_dir, exist_ok=True)
    drugs_tsv = os.path.join(out_dir, 'drugs.tsv')
    syn_tsv = os.path.join(out_dir, 'synonyms.tsv')
    print("Streaming parse:", xml_file)
    ctx = etree.iterparse(xml_file, events=('end',))
    dcount = 0
    with open(drugs_tsv,'w',encoding='utf-8',newline='') as df, \
         open(syn_tsv,'w',encoding='utf-8',newline='') as sf:
        dw = csv.writer(df, delimiter='\t')
        sw = csv.writer(sf, delimiter='\t')
        dw.writerow(['drugbank_id','name','type','description','cas','unii','state'])
        sw.writerow(['drugbank_id','synonym'])
        for event, el in ctx:
            tag = el.tag
            if tag.endswith('}drug') or tag == 'drug':
                dbid = ''
                for xid in el.findall('.//{*}drugbank-id'):
                    if xid.get('primary') == 'true':
                        dbid = xid.text.strip() if xid.text else ''
                        break
                if not dbid:
                    xid = el.find('.//{*}drugbank-id')
                    dbid = xid.text.strip() if xid is not None and xid.text else ''
                name = (el.find('.//{*}name').text.strip() if el.find('.//{*}name') is not None and el.find('.//{*}name').text else '')
                dtype = (el.get('type') or '').strip()
                desc = (el.find('.//{*}description').text.strip() if el.find('.//{*}description') is not None and el.find('.//{*}description').text else '')
                cas = (el.find('.//{*}cas-number').text.strip() if el.find('.//{*}cas-number') is not None and el.find('.//{*}cas-number').text else '')
                unii = (el.find('.//{*}unii').text.strip() if el.find('.//{*}unii') is not None and el.find('.//{*}unii').text else '')
                state = (el.find('.//{*}state').text.strip() if el.find('.//{*}state') is not None and el.find('.//{*}state').text else '')
                if dbid:
                    dw.writerow([dbid, name, dtype, desc, cas, unii, state])
                    for s in el.findall('.//{*}synonym'):
                        if s.text:
                            sw.writerow([dbid, s.text.strip()])
                dcount += 1
                if dcount % 500 == 0:
                    print("Processed drugs:", dcount)
                # free memory
                el.clear()
                while el.getprevious() is not None:
                    del el.getparent()[0]
    print("Wrote TSVs to", out_dir)
    return drugs_tsv, syn_tsv

def load_to_mysql(drugs_tsv, syn_tsv):
    print("Connecting to DB...")
    conn = pymysql.connect(host=args.db_host, port=args.db_port, user=args.db_user,
                           password=args.db_password, charset='utf8mb4', local_infile=1)
    cur = conn.cursor()

    # <<< สำคัญ: เลือกฐานข้อมูลก่อนรัน DROP / CREATE / LOAD
    cur.execute(f"USE `{args.db_name}`;")

    if args.drop:
        cur.execute("DROP TABLE IF EXISTS drugs, synonyms;")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS drugs (
      id BIGINT AUTO_INCREMENT PRIMARY KEY,
      drugbank_id VARCHAR(50) UNIQUE,
      name TEXT,
      type VARCHAR(50),
      description LONGTEXT,
      cas_number VARCHAR(100),
      unii VARCHAR(100),
      state VARCHAR(50)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS synonyms (
      id BIGINT AUTO_INCREMENT PRIMARY KEY,
      drugbank_id VARCHAR(50),
      synonym TEXT,
      INDEX (drugbank_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)
    conn.commit()

    # --- safe LOAD for drugs.tsv ---
    safe_drugs_tsv = drugs_tsv.replace("'", "\\'")
    sql_drugs = (
        "LOAD DATA LOCAL INFILE '{}' "
        "INTO TABLE drugs "
        "CHARACTER SET utf8mb4 "
        "FIELDS TERMINATED BY '\\t' "
        "LINES TERMINATED BY '\\n' "
        "IGNORE 1 LINES "
        "(drugbank_id,name,type,description,cas_number,unii,state);"
    ).format(safe_drugs_tsv)
    cur.execute(sql_drugs)
    conn.commit()

    # --- safe LOAD for synonyms.tsv ---
    safe_syn_tsv = syn_tsv.replace("'", "\\'")
    sql_syn = (
        "LOAD DATA LOCAL INFILE '{}' "
        "INTO TABLE synonyms "
        "CHARACTER SET utf8mb4 "
        "FIELDS TERMINATED BY '\\t' "
        "LINES TERMINATED BY '\\n' "
        "IGNORE 1 LINES "
        "(drugbank_id,synonym);"
    ).format(safe_syn_tsv)
    cur.execute(sql_syn)
    conn.commit()

    cur.close()
    conn.close()
    print("Loaded TSVs into MySQL.")

def main():
    z = args.zip
    xmlfile = extract_xml(z, args.xml_name)
    try:
        drugs_tsv, syn_tsv = stream_parse_to_tsv(xmlfile, args.out_dir)
        load_to_mysql(drugs_tsv, syn_tsv)
    finally:
        # cleanup extracted xml if present and in tmp dir
        try:
            if xmlfile and xmlfile.startswith('/tmp'):
                os.remove(xmlfile)
        except Exception:
            pass

if __name__ == '__main__':
    main()
