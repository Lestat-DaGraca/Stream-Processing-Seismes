document.addEventListener('DOMContentLoaded', () => {
    // --- Carte Leaflet ---
    const map = L.map('map').setView([20, 0], 2);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 19,
        attribution: '© OpenStreetMap'
    }).addTo(map);

    const listContainer = document.getElementById('earthquake-list');
    const alertZone = document.getElementById('alert-message');

    const statCount = document.getElementById('stat-count');
    const statAvg = document.getElementById('stat-avg');
    const statMax = document.getElementById('stat-max');

    let markers = [];
    let earthquakes = []; // Variable globale pour stocker les séismes
    let clusterLayers = [];

    const injectBtn = document.getElementById('btn-inject-csv');
    if (injectBtn) {
        injectBtn.addEventListener('click', function() {
            if (!confirm("Voulez-vous vraiment injecter 500 séismes depuis le CSV vers Kafka ?")) return;

            injectBtn.disabled = true;
            injectBtn.innerText = "⏳ Injection en cours...";

            fetch('/inject-csv')
                .then(response => response.json())
                .then(data => {
                    alert(data.status || data.message);
                })
                .catch(error => {
                    console.error('Erreur:', error);
                    alert("Erreur lors de l'injection.");
                })
                .finally(() => {
                    injectBtn.disabled = false;
                    injectBtn.innerText = "🚀 Injecter 500 Séismes";
                });
        });
    }

    function clearMarkers() {
        markers.forEach(m => map.removeLayer(m));
        markers = [];
    }

    async function updateStats(list) {
        try {
            const res = await fetch("/stats/global");
            const data = await res.json();

            statCount.textContent = data.count;
            statAvg.textContent = data.average.toFixed(2);

            // Vérifie que list existe et n'est pas vide
            if (list && list.length > 0) {
                const max = Math.max(...list.map(e => e.magnitude));
                statMax.textContent = max;
            } else {
                statMax.textContent = "N/A";
            }

        } catch (err) {
            console.error("Erreur récupération stats globales:", err);
        }
    }

    function displayEarthquakes(list) {
        listContainer.innerHTML = "";
        clearMarkers();
        const sortedList = [...list].sort((a, b) => {
            const dateA = new Date(a.date);
            const dateB = new Date(b.date);
            return dateB - dateA; // Ordre décroissant
        });

        sortedList.forEach(eq => {
            const card = document.createElement('div');
            card.classList.add('earthquake-card');
            card.innerHTML = `
                <div class="eq-info">
                    <span class="eq-location">${eq.name}</span>
                    <span class="eq-magnitude">Magnitude : ${eq.magnitude}</span>
                    <span class="eq-date">${eq.date}</span>
                </div>
                <div class="eq-badge ${eq.magnitude >= 7 ? 'high' : eq.magnitude >= 5 ? 'medium' : 'low'}">
                    ${eq.magnitude}
                </div>
            `;
            listContainer.prepend(card);

            const marker = L.marker(eq.coords).addTo(map).bindPopup(`<b>${eq.name}</b><br>Magnitude ${eq.magnitude}`);
            markers.push(marker);
        });
        updateStats(sortedList);

        // Zone d'alerte
        const hasStrong = list.some(eq => eq.magnitude >= 7);
        const alertDiv = document.querySelector('.alert-zone');
        if (hasStrong) {
            alertZone.textContent = "⚠️ Alerte : Séisme majeur détecté !";
            alertDiv.classList.add('active');
            alertDiv.classList.remove('safe');
        } else {
            alertZone.textContent = "✅ Aucune alerte en cours.";
            alertDiv.classList.add('safe');
            alertDiv.classList.remove('active');
        }
    }

    function applyFilters() {
        const minMag = parseFloat(document.getElementById('magnitude').value);
        const region = document.getElementById('region').value;
        const date = document.getElementById('date').value;

        let filtered = earthquakes.filter(eq => eq.magnitude >= minMag);
        if(region !== "all") filtered = filtered.filter(eq => eq.region === region);
        if(date) filtered = filtered.filter(eq => eq.date === date);

        displayEarthquakes(filtered);
    }

    async function loadEarthquakes() {
        try {
            const res = await fetch('/data');
            const data = await res.json();

            earthquakes = data.map(eq => {
                const dateStr = eq.date.replace(/(\.\d{3})\d+$/, '$1');
                const dateObj = new Date(dateStr);
                
                return {
                    name: eq.name,
                    coords: eq.coords,
                    magnitude: eq.magnitude,
                    date: dateObj.toLocaleString('fr-FR', {
                        day: '2-digit',
                        month: 'long',
                        year: 'numeric',
                        hour: '2-digit',
                        minute: '2-digit',
                        second: '2-digit'
                    }),
                    region: eq.region
                };
            });

            displayEarthquakes(earthquakes);

        } catch (err) {
            console.error("Erreur lors du chargement des séismes :", err);
        }
    }

        async function loadClusters() {
        try {
            const res = await fetch('/clusters');
            const clusters = await res.json();

            clearClusterLayers();

            clusters.forEach((cluster, idx) => {
                const color = getClusterColor(idx);

                // Dessiner chaque point du cluster
                cluster.points.forEach(point => {
                    const circle = L.circleMarker([point.lat, point.lon], {
                        radius: Math.max(4, point.mag * 1.5),
                        color: color,
                        fillColor: color,
                        fillOpacity: 0.6,
                        weight: 2
                    }).bindPopup(`
                        <strong>Cluster #${cluster.id}</strong><br>
                        Région: ${cluster.region}<br>
                        Points dans le cluster: ${cluster.size}<br>
                        Magnitude moyenne: ${cluster.avg_magnitude}<br>
                        <hr>
                        <em>Ce point:</em><br>
                        Magnitude: ${point.mag}
                    `);
                    
                    circle.addTo(map);
                    clusterLayers.push(circle);
                });

                // Dessiner le centre du cluster (marqueur plus visible)
                if (cluster.center) {
                    const centerMarker = L.circleMarker(cluster.center, {
                        radius: 10,
                        color: color,
                        fillColor: 'white',
                        fillOpacity: 0.9,
                        weight: 3
                    }).bindPopup(`
                        <strong>📍 Centre du Cluster #${cluster.id}</strong><br>
                        Région: ${cluster.region}<br>
                        Nombre de séismes: ${cluster.size}<br>
                        Magnitude moyenne: ${cluster.avg_magnitude}
                    `);
                    
                    centerMarker.addTo(map);
                    clusterLayers.push(centerMarker);
                }
            });

            console.log(`✅ ${clusters.length} clusters DBSCAN affichés`);

        } catch (err) {
            console.error("Erreur chargement clusters :", err);
        }
    }

    function clearClusterLayers() {
        clusterLayers.forEach(layer => map.removeLayer(layer));
        clusterLayers = [];
    }

    function getClusterColor(i) {
        const colors = [
            '#e41a1c', '#377eb8', '#4daf4a',
            '#984ea3', '#ff7f00', '#a65628',
            '#f781bf', '#999999'
        ];
        return colors[i % colors.length];
    }

    // Initial
    loadEarthquakes();
    loadClusters();
    
    setInterval(loadEarthquakes, 10000);
    setInterval(loadClusters, 20000);
    setInterval(() => updateStats(earthquakes), 15000);

    // Event
    document.getElementById('apply-filters').addEventListener('click', applyFilters);
});