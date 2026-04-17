<template>
  <div class="page-container">
    <div class="page-header">
      <h2 class="page-title">Charts & Visualization</h2>
      <p class="page-desc">Log statistics and trends visualization</p>
    </div>

    <el-row :gutter="20">
      <!-- Log Volume Trend -->
      <el-col :span="12">
        <el-card>
          <template #header>Log Volume Trend</template>
          <div ref="logVolumeChart" style="height: 300px;"></div>
        </el-card>
      </el-col>

      <!-- Error Distribution -->
      <el-col :span="12">
        <el-card>
          <template #header>Error Distribution by Type</template>
          <div ref="errorPieChart" style="height: 300px;"></div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="20" class="mt-20">
      <!-- Severity Heatmap -->
      <el-col :span="24">
        <el-card>
          <template #header>Error Timeline Heatmap</template>
          <div ref="heatmapChart" style="height: 300px;"></div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="20" class="mt-20">
      <!-- Top Sources -->
      <el-col :span="8">
        <el-card>
          <template #header>Top Source Hosts</template>
          <div ref="sourceBarChart" style="height: 300px;"></div>
        </el-card>
      </el-col>

      <!-- Program Distribution -->
      <el-col :span="8">
        <el-card>
          <template #header>Program Distribution</template>
          <div ref="programChart" style="height: 300px;"></div>
        </el-card>
      </el-col>

      <!-- Daily Stats -->
      <el-col :span="8">
        <el-card>
          <template #header>Daily Statistics</template>
          <el-table :data="dailyStats" size="small">
            <el-table-column prop="date" label="Date" width="100" />
            <el-table-column prop="total" label="Total" />
            <el-table-column prop="errors" label="Errors">
              <template #default="{ row }">
                <span :class="{ 'text-danger': row.errors > 100 }">{{ row.errors }}</span>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import * as echarts from 'echarts'

const logVolumeChart = ref()
const errorPieChart = ref()
const heatmapChart = ref()
const sourceBarChart = ref()
const programChart = ref()

const dailyStats = ref([
  { date: '04-17', total: '45.6K', errors: 128 },
  { date: '04-16', total: '42.3K', errors: 95 },
  { date: '04-15', total: '38.1K', errors: 72 },
  { date: '04-14', total: '35.8K', errors: 45 },
  { date: '04-13', total: '40.2K', errors: 63 },
])

function initCharts() {
  // Log Volume Chart
  const volumeChart = echarts.init(logVolumeChart.value)
  volumeChart.setOption({
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: ['00:00', '04:00', '08:00', '12:00', '16:00', '20:00', '24:00'] },
    yAxis: { type: 'value' },
    series: [
      { name: 'Logs', type: 'line', smooth: true, data: [500, 800, 2500, 3000, 2800, 1500, 600], areaStyle: { opacity: 0.3 } },
      { name: 'Errors', type: 'line', smooth: true, data: [10, 15, 45, 50, 40, 25, 12] }
    ]
  })

  // Error Pie Chart
  const pieChart = echarts.init(errorPieChart.value)
  pieChart.setOption({
    tooltip: { trigger: 'item' },
    series: [{
      type: 'pie', radius: '60%',
      data: [
        { value: 40, name: 'Network' },
        { value: 35, name: 'Server' },
        { value: 25, name: 'K8S' }
      ]
    }]
  })

  // Heatmap
  const heatChart = echarts.init(heatmapChart.value)
  heatChart.setOption({
    tooltip: { position: 'top' },
    grid: { top: 10, bottom: 30, left: 60, right: 10 },
    xAxis: { type: 'category', data: ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'], splitArea: { show: true } },
    yAxis: { type: 'category', data: ['00-04', '04-08', '08-12', '12-16', '16-20', '20-24'], splitArea: { show: true } },
    visualMap: { min: 0, max: 50, calculable: true, orient: 'horizontal', left: 'center', bottom: 0 },
    series: [{
      type: 'heatmap',
      data: [
        [0, 0, 5], [0, 1, 3], [0, 2, 15], [0, 3, 20], [0, 4, 18], [0, 5, 8],
        [1, 0, 4], [1, 1, 2], [1, 2, 12], [1, 3, 18], [1, 4, 15], [1, 5, 6],
        [2, 0, 6], [2, 1, 4], [2, 2, 20], [2, 3, 25], [2, 4, 22], [2, 5, 10],
        [3, 0, 3], [3, 1, 2], [3, 2, 10], [3, 3, 15], [3, 4, 12], [3, 5, 5],
        [4, 0, 5], [4, 1, 3], [4, 2, 18], [4, 3, 22], [4, 4, 20], [4, 5, 9],
        [5, 0, 2], [5, 1, 1], [5, 2, 5], [5, 3, 8], [5, 4, 6], [5, 5, 3],
        [6, 0, 1], [6, 1, 0], [6, 2, 3], [6, 3, 5], [6, 4, 4], [6, 5, 2]
      ],
      label: { show: true }
    }]
  })

  // Source Bar Chart
  const barChart = echarts.init(sourceBarChart.value)
  barChart.setOption({
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'value' },
    yAxis: { type: 'category', data: ['web-01', 'db-01', 'switch-01', 'pod-api', 'kube-01'] },
    series: [{ type: 'bar', data: [120, 95, 80, 65, 50] }]
  })

  // Program Chart
  const progChart = echarts.init(programChart.value)
  progChart.setOption({
    tooltip: { trigger: 'item' },
    series: [{
      type: 'pie', radius: ['40%', '70%'],
      data: [
        { value: 100, name: 'nginx' },
        { value: 80, name: 'kernel' },
        { value: 60, name: 'sshd' },
        { value: 40, name: 'mysql' },
        { value: 30, name: 'kubelet' }
      ]
    }]
  })
}

onMounted(() => {
  initCharts()
})
</script>

<style scoped lang="scss">
.text-danger {
  color: #f56c6c;
  font-weight: bold;
}
</style>