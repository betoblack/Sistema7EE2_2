id="dashboardjs"
const ctx = document.getElementById("grafica");

new Chart(ctx, {
    type: "bar",

    data: {
        labels: ["Préstamos", "Pagos", "Perdidos", "Logins"],

        datasets: [{
            label: "Estadísticas del Sistema",

            data: [
                estadisticas.prestamos,
                estadisticas.pagos,
                estadisticas.perdidos,
                estadisticas.logins
            ],

            borderWidth: 1
        }]
    },

    options: {
        responsive: true,

        plugins: {
            legend: {
                display: true
            }
        }
    }
});