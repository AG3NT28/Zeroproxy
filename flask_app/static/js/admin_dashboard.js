// ─── Admin dashboard: department attendance bar chart (Chart.js) ───
;(function () {
  const data = window.ADMIN_CHART_DATA
  const canvas = document.getElementById('dept-chart')
  if (!data || !canvas || !window.Chart) return

  new Chart(canvas, {
    type: 'bar',
    data: {
      labels: data.labels,
      datasets: [{
        label: 'Attendance %',
        data: data.data,
        backgroundColor: 'rgba(99, 102, 241, 0.55)',
        borderColor: 'rgba(99, 102, 241, 1)',
        borderWidth: 1,
        borderRadius: 6,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: { y: { beginAtZero: true, max: 100, ticks: { callback: v => v + '%' } } },
      plugins: { legend: { display: false } },
    },
  })
})()
