document.addEventListener('DOMContentLoaded', function() {
    const regionColors = [
        '#38bdf8', '#f472b6', '#a78bfa',
        '#34d399', '#fbbf24', '#f87171',
        '#818cf8', '#c084fc', '#2dd4bf'
    ];

    function getColorForIndex(index) {
        return regionColors[index % regionColors.length];
    }

    const ctx = document.getElementById('quakeCountChart').getContext('2d');

    Chart.defaults.color = '#94a3b8';
    Chart.defaults.borderColor = 'rgba(255, 255, 255, 0.1)';
    Chart.defaults.font.family = "'Inter', sans-serif";

    const chart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: [],
            datasets: [{
                label: 'Nombre de séismes',
                data: [],
                backgroundColor: [],
                borderWidth: 1
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: 'rgba(15, 23, 42, 0.9)',
                    titleColor: '#f8fafc',
                    bodyColor: '#cbd5e1',
                    borderColor: 'rgba(255, 255, 255, 0.1)',
                    borderWidth: 1,
                    padding: 10,
                    displayColors: false,
                }
            },
            scales: {
                x: {
                    title: { display: true, text: 'Région' },
                    grid: { display: false }
                },
                y: {
                    beginAtZero: true,
                    title: { display: true, text: 'Nombre de séismes' },
                    ticks: { precision: 0 }
                }
            }
        }
    });

    const allRegions = [
        "Antarctica", "NorthAmerica", "SouthAmerica",
        "Europe", "Africa", "Asia", "Oceania", "Unknown"
    ];

    async function fetchChartData() {
        try {
            let response = await fetch('/stats/trends');
            let rawData = await response.json();

            if (!Array.isArray(rawData)) {
                console.warn("Aucune donnée reçue");
                return;
            }

            const counts = {};
            allRegions.forEach(r => counts[r] = 0);

            rawData.forEach(item => {
                const region = item.region;
                if (counts.hasOwnProperty(region)) {
                    counts[region] = item.count || 0;
                }
            });

            const regions = allRegions;
            const dataValues = regions.map(r => counts[r]);
            const colors = regions.map((_, i) => getColorForIndex(i));

            chart.data.labels = regions;
            chart.data.datasets[0].data = dataValues;
            chart.data.datasets[0].backgroundColor = colors;
            chart.update();

        } catch (error) {
            console.error("Erreur chargement graphique:", error);
        }
    }

    async function fetchTopKGlobal() {
        try {
            const response = await fetch('/stats/topk/global');
            const data = await response.json();
            
            const container = document.getElementById('topk-global');
            if (!container) return;
            
            container.innerHTML = '<h3 class="text-xl font-semibold mb-4 text-sky-300">🌍 Top 10 Séismes Globaux</h3>';
            
            const list = document.createElement('div');
            list.className = 'space-y-2';
            
            if (data.length === 0) {
                list.innerHTML = '<p class="text-slate-400 text-sm">Aucune donnée disponible</p>';
            } else {
                data.forEach(quake => {
                    const item = document.createElement('div');
                    item.className = 'bg-slate-700/50 p-3 rounded-lg hover:bg-slate-700/70 transition-colors';
                    item.innerHTML = `
                        <div class="flex justify-between items-center">
                            <span class="font-bold text-sky-400">#${quake.rank}</span>
                            <span class="text-2xl font-bold text-red-400">M${quake.magnitude}</span>
                        </div>
                        <div class="text-sm text-slate-300 mt-1">${quake.place}</div>
                        <div class="text-xs text-slate-400 mt-1">
                            ${new Date(quake.time).toLocaleString('fr-FR')} - ${quake.region}
                        </div>
                    `;
                    list.appendChild(item);
                });
            }
            
            container.appendChild(list);
        } catch (error) {
            console.error('Erreur Top-K Global:', error);
            const container = document.getElementById('topk-global');
            if (container) {
                container.innerHTML = '<p class="text-red-400">Erreur de chargement</p>';
            }
        }
    }

    async function fetchTopKByRegion() {
        try {
            const response = await fetch('/stats/topk/region');
            const data = await response.json();
            
            const container = document.getElementById('topk-regions');
            if (!container) return;
            
            container.innerHTML = '<h3 class="text-xl font-semibold mb-4 text-sky-300">📊 Top 10 par Région</h3>';
            
            const regionsToDisplay = allRegions.filter(r => r !== "Unknown");
        
            if (regionsToDisplay.length === 0) {
                container.innerHTML += '<p class="text-slate-400 text-sm">Aucune donnée disponible</p>';
                return;
            }
            
            regionsToDisplay.forEach(region => {
                const regionDiv = document.createElement('div');
                regionDiv.className = 'mb-6';
                
                const title = document.createElement('h4');
                title.className = 'text-lg font-semibold text-sky-300 mb-2 flex items-center';
                title.innerHTML = `
                    <span class="inline-block w-3 h-3 rounded-full mr-2" 
                          style="background-color: ${getColorForIndex(allRegions.indexOf(region))}"></span>
                    ${region}
                `;
                regionDiv.appendChild(title);
                
                const list = document.createElement('div');
                list.className = 'space-y-2';
                
                const regionData = data[region] || [];

                if (regionData.length === 0) {
                    list.innerHTML = '<p class="text-slate-400 text-xs">Aucun séisme</p>';
                } else {
                    regionData.forEach(quake => {
                        const item = document.createElement('div');
                        item.className = 'bg-slate-700/30 p-2 rounded hover:bg-slate-700/50 transition-colors';
                        item.innerHTML = `
                            <div class="flex justify-between items-center">
                                <div class="flex-1">
                                    <span class="text-sm font-medium text-slate-200">
                                        #${quake.rank} ${quake.place}
                                    </span>
                                    <div class="text-xs text-slate-400 mt-0.5">
                                        ${new Date(quake.time).toLocaleString('fr-FR')}
                                    </div>
                                </div>
                                <span class="font-bold text-red-400 ml-2">M${quake.magnitude}</span>
                            </div>
                        `;
                        list.appendChild(item);
                    });
                }
                
                regionDiv.appendChild(list);
                container.appendChild(regionDiv);
            });
        } catch (error) {
            console.error('Erreur Top-K Régions:', error);
            const container = document.getElementById('topk-regions');
            if (container) {
                container.innerHTML = '<p class="text-red-400">Erreur de chargement</p>';
            }
        }
    }

    fetchChartData();
    fetchTopKGlobal();
    fetchTopKByRegion();
    
    setInterval(() => {
        fetchChartData();
        fetchTopKGlobal();
        fetchTopKByRegion();
    }, 10000);
});