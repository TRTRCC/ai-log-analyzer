<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">AI Configuration</h2>
      <p class="page-desc">Configure AI service providers and models</p>
    </div>

    <!-- Providers -->
    <el-card>
      <template #header>
        <div class="flex-between">
          <span>AI Providers</span>
          <el-button type="primary" size="small" @click="showAddProvider">
            <el-icon><Plus /></el-icon>
            Add Provider
          </el-button>
        </div>
      </template>

      <el-table :data="providers" stripe>
        <el-table-column prop="display_name" label="Name" width="200" />
        <el-table-column prop="provider_type" label="Type" width="120">
          <template #default="{ row }">
            <el-tag>{{ row.provider_type }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="api_endpoint" label="API Endpoint" show-overflow-tooltip />
        <el-table-column prop="is_active" label="Status" width="100">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'danger'">
              {{ row.is_active ? 'Active' : 'Disabled' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="is_default" label="Default" width="80">
          <template #default="{ row }">
            <el-icon v-if="row.is_default" color="#409EFF"><Star /></el-icon>
          </template>
        </el-table-column>
        <el-table-column label="Actions" width="200" fixed="right">
          <template #default="{ row }">
            <el-button size="small" link @click="editProvider(row)">Edit</el-button>
            <el-button size="small" link @click="setAsDefault(row)">Set Default</el-button>
            <el-button size="small" link type="danger" @click="deleteProvider(row)">Delete</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- Models -->
    <el-card class="mt-20">
      <template #header>
        <div class="flex-between">
          <span>AI Models</span>
          <el-button type="primary" size="small" @click="showAddModel">
            <el-icon><Plus /></el-icon>
            Add Model
          </el-button>
        </div>
      </template>

      <el-table :data="models" stripe>
        <el-table-column prop="display_name" label="Name" width="200" />
        <el-table-column prop="provider_name" label="Provider" width="150" />
        <el-table-column prop="model_name" label="Model ID" width="200" />
        <el-table-column prop="max_tokens" label="Max Tokens" width="120" />
        <el-table-column prop="cost_per_1k_input" label="Input Cost" width="120">
          <template #default="{ row }">
            ${{ row.cost_per_1k_input || '0' }}/1K
          </template>
        </el-table-column>
        <el-table-column prop="is_active" label="Status" width="100">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'danger'">
              {{ row.is_active ? 'Active' : 'Disabled' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="Actions" width="150" fixed="right">
          <template #default="{ row }">
            <el-button size="small" link @click="editModel(row)">Edit</el-button>
            <el-button size="small" link type="danger" @click="deleteModel(row)">Delete</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- Provider Dialog -->
    <el-dialog v-model="providerDialogVisible" :title="editingProvider ? 'Edit Provider' : 'Add Provider'" width="600px">
      <el-form :model="providerForm" label-width="120px">
        <el-form-item label="Name" required>
          <el-input v-model="providerForm.display_name" />
        </el-form-item>
        <el-form-item label="Type" required>
          <el-select v-model="providerForm.provider_type">
            <el-option label="Claude (Anthropic)" value="claude" />
            <el-option label="OpenAI" value="openai" />
            <el-option label="Azure OpenAI" value="azure_openai" />
            <el-option label="Local Model" value="local" />
            <el-option label="Custom" value="custom" />
          </el-select>
        </el-form-item>
        <el-form-item label="API Endpoint">
          <el-input v-model="providerForm.api_endpoint" placeholder="https://api.example.com" />
        </el-form-item>
        <el-form-item label="API Key" required>
          <el-input v-model="providerForm.api_key" type="password" show-password />
        </el-form-item>
        <el-form-item label="Active">
          <el-switch v-model="providerForm.is_active" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="providerDialogVisible = false">Cancel</el-button>
        <el-button type="primary" @click="saveProvider">Save</el-button>
      </template>
    </el-dialog>

    <!-- Model Dialog -->
    <el-dialog v-model="modelDialogVisible" :title="editingModel ? 'Edit Model' : 'Add Model'" width="500px">
      <el-form :model="modelForm" label-width="120px">
        <el-form-item label="Provider" required>
          <el-select v-model="modelForm.provider_id">
            <el-option v-for="p in providers" :key="p.id" :label="p.display_name" :value="p.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="Display Name" required>
          <el-input v-model="modelForm.display_name" />
        </el-form-item>
        <el-form-item label="Model ID" required>
          <el-input v-model="modelForm.model_name" placeholder="claude-3-5-sonnet" />
        </el-form-item>
        <el-form-item label="Max Tokens">
          <el-input-number v-model="modelForm.max_tokens" :min="1000" :max="100000" />
        </el-form-item>
        <el-form-item label="Input Cost">
          <el-input v-model="modelForm.cost_per_1k_input" placeholder="0.003" />
        </el-form-item>
        <el-form-item label="Output Cost">
          <el-input v-model="modelForm.cost_per_1k_output" placeholder="0.015" />
        </el-form-item>
        <el-form-item label="Active">
          <el-switch v-model="modelForm.is_active" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="modelDialogVisible = false">Cancel</el-button>
        <el-button type="primary" @click="saveModel">Save</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

const providerDialogVisible = ref(false)
const modelDialogVisible = ref(false)
const editingProvider = ref(null)
const editingModel = ref(null)

const providerForm = reactive({
  display_name: '',
  provider_type: 'claude',
  api_endpoint: '',
  api_key: '',
  is_active: true
})

const modelForm = reactive({
  provider_id: '',
  display_name: '',
  model_name: '',
  max_tokens: 4000,
  cost_per_1k_input: '',
  cost_per_1k_output: '',
  is_active: true
})

const providers = ref([
  { id: 'p1', display_name: 'Claude API', provider_type: 'claude', api_endpoint: 'https://api.anthropic.com', is_active: true, is_default: true },
  { id: 'p2', display_name: 'OpenAI', provider_type: 'openai', api_endpoint: 'https://api.openai.com/v1', is_active: true, is_default: false },
  { id: 'p3', display_name: 'Local Ollama', provider_type: 'local', api_endpoint: 'http://localhost:11434', is_active: false, is_default: false },
])

const models = ref([
  { id: 'm1', display_name: 'Claude 3.5 Sonnet', provider_name: 'Claude API', model_name: 'claude-3-5-sonnet', max_tokens: 8192, cost_per_1k_input: 0.003, is_active: true },
  { id: 'm2', display_name: 'GPT-4', provider_name: 'OpenAI', model_name: 'gpt-4', max_tokens: 8192, cost_per_1k_input: 0.03, is_active: true },
])

function showAddProvider() {
  editingProvider.value = null
  Object.assign(providerForm, { display_name: '', provider_type: 'claude', api_endpoint: '', api_key: '', is_active: true })
  providerDialogVisible.value = true
}

function editProvider(provider) {
  editingProvider.value = provider
  Object.assign(providerForm, provider)
  providerDialogVisible.value = true
}

async function saveProvider() {
  ElMessage.success(editingProvider.value ? 'Provider updated' : 'Provider added')
  providerDialogVisible.value = false
}

async function setAsDefault(provider) {
  providers.value.forEach(p => p.is_default = false)
  provider.is_default = true
  ElMessage.success(`${provider.display_name} set as default`)
}

async function deleteProvider(provider) {
  await ElMessageBox.confirm(`Delete provider ${provider.display_name}?`, 'Confirm', { type: 'danger' })
  providers.value = providers.value.filter(p => p.id !== provider.id)
  ElMessage.success('Provider deleted')
}

function showAddModel() {
  editingModel.value = null
  Object.assign(modelForm, { provider_id: '', display_name: '', model_name: '', max_tokens: 4000, cost_per_1k_input: '', cost_per_1k_output: '', is_active: true })
  modelDialogVisible.value = true
}

function editModel(model) {
  editingModel.value = model
  Object.assign(modelForm, model)
  modelDialogVisible.value = true
}

async function saveModel() {
  ElMessage.success(editingModel.value ? 'Model updated' : 'Model added')
  modelDialogVisible.value = false
}

async function deleteModel(model) {
  await ElMessageBox.confirm(`Delete model ${model.display_name}?`, 'Confirm', { type: 'danger' })
  models.value = models.value.filter(m => m.id !== model.id)
  ElMessage.success('Model deleted')
}
</script>