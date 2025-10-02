import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import axios from 'axios'

export interface Drug {
  id: string
  name: string
  created_at?: Date
}

export const useDrugStore = defineStore('drug', () => {
  // State
  const drugs = ref<Drug[]>([])
  const isLoading = ref(false)
  const error = ref<string | null>(null)

  // Getters
  const hasDrugs = computed(() => drugs.value.length > 0)
  const drugCount = computed(() => drugs.value.length)

  // Actions
  const addDrug = async (userId: string, drugId: string) => {
    try {
      isLoading.value = true
      error.value = null
      
      const response = await axios.post(`/user-drugs/${userId}`, {
        drugbank_id: drugId,
      })

      const newDrug: Drug = {
        id: response.data.user_drugs_id,
        name: response.data.drug_name,
        created_at: response.data.created_at ? new Date(response.data.created_at) : new Date()
      }

      drugs.value.push(newDrug)

      console.log(drugs.value)
      return { success: true, drug: newDrug }
    } catch (err: any) {
      error.value = err.response?.data?.message || 'Failed to add drug'
      return { success: false, error: error.value }
    } finally {
      isLoading.value = false
    }
  }

  const removeDrug = async (drugId: string) => {
    try {
      isLoading.value = true
      error.value = null


      await axios.delete(`/user-drugs/${drugId}`)

      const index = drugs.value.findIndex(drug => drug.id === drugId)
      if (index !== -1) {
        drugs.value.splice(index, 1)
      }

      return { success: true }
    } catch (err: any) {
      error.value = err.response?.data?.message || 'Failed to remove drug'
      return { success: false, error: error.value }
    } finally {
      isLoading.value = false
    }
  }

  const loadUserDrugs = async (userId?: string) => {
    try {
      isLoading.value = true
      error.value = null

      if (!userId) {
        return { success: false, error: 'User ID is required' }
      }

      const response = await axios.get(`/user-drugs/${userId}`)
      
      // Convert API response to Drug interface
      drugs.value = response.data.map((drug: any) => ({
        id: drug.id,
        name: drug.drug_name,
        created_at: drug.created_at ? new Date(drug.created_at) : new Date()
      }))

      return { success: true }
    } catch (err: any) {
      error.value = err.response?.data?.message || 'Failed to load drugs'
      return { success: false, error: error.value }
    } finally {
      isLoading.value = false
    }
  }

  const clearDrugs = () => {
    drugs.value = []
  }

  const clearError = () => {
    error.value = null
  }

  return {
    // State
    drugs,
    isLoading,
    error,
    
    // Getters
    hasDrugs,
    drugCount,
    
    // Actions
    addDrug,
    removeDrug,
    loadUserDrugs,
    clearDrugs,
    clearError
  }
})
