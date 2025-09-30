#!/usr/bin/env python3
import argparse, zipfile, os, csv, time, tempfile, shutil
from lxml import etree
import pymysql

parser = argparse.ArgumentParser()
parser.add_argument('-z','--zip', required=True)
parser.add_argument('--xml-name', default=None)
parser.add_argument('--out-dir', default='/tmp/drugbank_tmp_csv')
parser.add_argument('--db-host', default='127.0.0.1')
parser.add_argument('--db-port', type=int, default=3306)
parser.add_argument('--db-user', default='root')
parser.add_argument('--db-password', default='P@ssw0rd')
parser.add_argument('--db-name', default='DrugBank')
args = parser.parse_args()

os.makedirs(args.out_dir, exist_ok=True)
tsv_path = os.path.join(args.out_dir, 'drug_interactions.tsv')

def extract_xml(zip_path, xml_name=None):
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
            with z.open(target) as src, open(os.path.join(tmpdir, os.path.basename(target)), 'wb') as dst:
                shutil.copyfileobj(src, dst)
            return os.path.join(tmpdir, os.path.basename(target))
    except Exception:
        try:
            shutil.rmtree(tmpdir)
        except Exception:
            pass
        raise

def stream_interactions(xml_file, out_tsv):
    # ensure output dir exists
    os.makedirs(os.path.dirname(out_tsv), exist_ok=True)
    count = 0
    with open(out_tsv,'w',encoding='utf-8',newline='') as f:
        w = csv.writer(f, delimiter='\t')
        w.writerow(['drugbank_id','interacts_with_drugbank_id','interacts_with_name','description'])
        context = etree.iterparse(xml_file, events=('end',))
        for event, drug in context:
            tag = drug.tag
            if tag.endswith('}drug') or tag == 'drug':
                dbid = ''
                for el in drug.findall('.//{*}drugbank-id'):
                    if el.get('primary') == 'true':
                        dbid = el.text.strip() if el.text else ''
                        break
                if not dbid:
                    el = drug.find('.//{*}drugbank-id')
                    dbid = el.text.strip() if el is not None and el.text else ''
                for di in drug.findall('.//{*}drug-interactions/{*}drug-interaction'):
                    ref = di.find('{*}drugbank-id')
                    name = di.find('{*}name')
                    desc = di.find('{*}description')
                    ref_id = ref.text.strip() if ref is not None and ref.text else ''
                    name_text = name.text.strip() if name is not None and name.text else ''
                    desc_text = desc.text.strip() if desc is not None and desc.text else ''
                    if dbid and (ref_id or name_text or desc_text):
                        w.writerow([dbid, ref_id, name_text, desc_text])
                count += 1
                if count % 500 == 0:
                    print("Processed drugs:", count)
                drug.clear()
                while drug.getprevious() is not None:
                    del drug.getparent()[0]
    print("Wrote interactions TSV:", out_tsv)

def load_to_mysql(tsv_file):
    print("Connecting to DB to load interactions...")
    conn = pymysql.connect(host=args.db_host, port=args.db_port, user=args.db_user,
                           password=args.db_password, charset='utf8mb4', local_infile=1)
    cur = conn.cursor()
    cur.execute(f"USE `{args.db_name}`;")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS drug_interactions (
      id BIGINT AUTO_INCREMENT PRIMARY KEY,
      drugbank_id VARCHAR(50) NOT NULL,
      interacts_with_drugbank_id VARCHAR(50),
      interacts_with_name TEXT,
      description TEXT,
      UNIQUE KEY (drugbank_id, interacts_with_drugbank_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)
    conn.commit()

    safe_tsv = tsv_file.replace("'", "\\'")
    sql = (
        "LOAD DATA LOCAL INFILE '{}' "
        "INTO TABLE drug_interactions "
        "CHARACTER SET utf8mb4 "
        "FIELDS TERMINATED BY '\\t' "
        "LINES TERMINATED BY '\\n' "
        "IGNORE 1 LINES "
        "(drugbank_id, interacts_with_drugbank_id, interacts_with_name, description)"
    ).format(safe_tsv)
    print("Running LOAD DATA ...")
    cur.execute(sql)
    conn.commit()
    cur.close()
    conn.close()
    print("Loaded interactions into DB.")

def main():
    zip_path = args.zip
    xml_file = extract_xml(zip_path, args.xml_name)
    try:
        stream_interactions(xml_file, tsv_path)
        load_to_mysql(tsv_path)
    finally:
        try:
            if xml_file and xml_file.startswith('/tmp'):
                os.remove(xml_file)
        except Exception:
            pass

if __name__ == '__main__':
    t0 = time.time()
    main()
    print("Done in", round(time.time()-t0,1), "s")
