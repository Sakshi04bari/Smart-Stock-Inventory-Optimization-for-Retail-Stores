// Auto-refresh alerts every 10s
setInterval(() => {
    if (window.location.pathname === '/') {
        fetch('/api/alerts?n=200')
            .then(res => res.json())
            .then(alerts => {
                // Update summary cards
                const understock = alerts.filter(a => a.stock_alert === 'Restock Needed').length;
                const overstock = alerts.filter(a => a.stock_alert === 'Overstock').length;
                const okstock = alerts.filter(a => a.stock_alert === 'Stock OK').length;
                
                document.querySelectorAll('.card h3')[0].textContent = understock;
                document.querySelectorAll('.card h3')[1].textContent = overstock;
                document.querySelectorAll('.card h3')[2].textContent = okstock;
                document.querySelectorAll('.card h3')[3].textContent = alerts.length;
            });
    }
}, 10000);

// Navbar active state
document.querySelectorAll('.nav-link').forEach(link => {
    if (link.href === window.location.href) {
        link.classList.add('active');
    }
});
