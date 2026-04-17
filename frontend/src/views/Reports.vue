<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">Reports</h2>
      <p class="page-desc">View and download analysis reports</p>
    </div>

    <!-- Report Filters -->
    <el-card>
      <el-form :model="filterForm" inline>
        <el-form-item label="Report Type">
          <el-select v-model="filterForm.reportType">
            <el-option label="Daily" value="daily" />
            <el-option label="Ad-hoc" value="adhoc" />
            <el-option label="All" value="" />
          </el-select>
        </el-form-item>
        <el-form-item label="Date Range">
          <el-date-picker
            v-model="filterForm.dateRange"
            type="daterange"
            range-separator="to"
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="filterReports">Filter</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- Reports List -->
    <el-card class="mt-20">
      <el-table :data="reports" stripe>
        <el-table-column prop="title" label="Title" />
        <el-table-column prop="report_type" label="Type" width="100">
          <template #default="{ row }">
            <el-tag :type="row.report_type === 'daily' ? 'primary' : 'success'">
              {{ row.report_type }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="report_date" label="Date" width="120" />
        <el-table-column prop="created_at" label="Generated" width="180" />
        <el-table-column prop="summary" label="Summary" show-overflow-tooltip />
        <el-table-column label="Actions" width="200" fixed="right">
          <template #default="{ row }">
            <el-button size="small" link @click="previewReport(row)">Preview</el-button>
            <el-button size="small" link @click="downloadReport(row)">Download</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-wrapper">
        <el-pagination
          v-model:current-page="currentPage"
          :total="total"
          layout="total, prev, pager, next"
        />
      </div>
    </el-card>

    <!-- Preview Dialog -->
    <el-dialog v-model="previewVisible" title="Report Preview" width="80%">
      <div v-if="currentReport" class="report-preview">
        <h2>{{ currentReport.title }}</h2>
        <el-divider />
        <div class="report-content">
          <pre>{{ currentReport.content }}</pre>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { ElMessage } from 'element-plus'

const previewVisible = ref(false)
const currentReport = ref(null)
const currentPage = ref(1)
const total = ref(50)

const filterForm = reactive({
  reportType: '',
  dateRange: []
})

const reports = ref([
  { id: '1', title: 'Daily Report - 2024-04-17', report_type: 'daily', report_date: '2024-04-17', created_at: '2024-04-17 08:00', summary: '128 errors, 3 security events' },
  { id: '2', title: 'Network Analysis Report', report_type: 'adhoc', report_date: '2024-04-16', created_at: '2024-04-16 14:30', summary: 'Network connectivity issues analyzed' },
  { id: '3', title: 'Daily Report - 2024-04-16', report_type: 'daily', report_date: '2024-04-16', created_at: '2024-04-16 08:00', summary: 'System performance normal' },
])

function filterReports() {
  ElMessage.info('Filtering reports...')
}

function previewReport(report) {
  currentReport.value = {
    ...report,
    content: `
# ${report.title}

## Summary
- Total Logs: 45,600
- Error Events: ${report.summary.split(',')[0]}
- Security Events: ${report.summary.split(',')[1] || 'None'}

## Key Findings
1. Network interface flapping detected on switch-01
2. High CPU usage on web-01 during peak hours
3. Multiple failed SSH login attempts detected

## Recommendations
1. Investigate switch-01 interface stability
2. Scale web-01 resources or optimize code
3. Review SSH access policies and implement fail2ban
    `
  }
  previewVisible.value = true
}

function downloadReport(report) {
  ElMessage.success(`Downloading ${report.title}...`)
}
</script>

<style scoped lang="scss">
.pagination-wrapper {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}

.report-preview {
  h2 {
    text-align: center;
    margin-bottom: 20px;
  }
}

.report-content {
  background-color: #f5f7fa;
  padding: 20px;
  border-radius: 4px;
  font-family: monospace;
  white-space: pre-wrap;
}
</style>