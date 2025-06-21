// static/script.js
document.addEventListener('DOMContentLoaded', function () {
    const backtestForm = document.getElementById('backtestForm');
    const resultsDiv = document.getElementById('results');
    const errorDiv = document.getElementById('errorDisplay');

    if (backtestForm) {
        backtestForm.addEventListener('submit', function (event) {
            event.preventDefault();
            resultsDiv.innerHTML = '<h2>Backtest Results:</h2><p>Running backtest...</p>';
            errorDiv.textContent = '';

            const formData = new FormData(backtestForm);

            // Log formData entries for debugging
            // for (let [key, value] of formData.entries()) {
            //     console.log(`${key}: ${value}`);
            // }

            fetch('/backtest', {
                method: 'POST',
                body: formData,
            })
            .then(response => {
                if (!response.ok) {
                    // Try to parse error from JSON response if available
                    return response.json().then(err => {
                        throw new Error(err.error || `Server error: ${response.statusText}`);
                    }).catch(() => {
                        // Fallback if error response is not JSON
                        throw new Error(`Server error: ${response.statusText} (Status: ${response.status})`);
                    });
                }
                return response.json();
            })
            .then(data => {
                if (data.error) {
                    errorDiv.textContent = `Error: ${data.error}`;
                    resultsDiv.innerHTML = '<h2>Backtest Results:</h2><p>Backtest failed.</p>';
                } else {
                    let resultsHTML = '<h2>Backtest Results:</h2>';
                    resultsHTML += '<pre>' + JSON.stringify(data, null, 2) + '</pre>';
                    resultsDiv.innerHTML = resultsHTML;
                }
            })
            .catch(error => {
                console.error('Fetch Error:', error);
                errorDiv.textContent = `Request Failed: ${error.message}`;
                resultsDiv.innerHTML = '<h2>Backtest Results:</h2><p>An error occurred while processing your request.</p>';
            });
        });
    }
});
