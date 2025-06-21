// static/script_static.js
document.addEventListener('DOMContentLoaded', function () {
    const backtestFormStatic = document.getElementById('backtestFormStatic');
    const resultsDivStatic = document.getElementById('resultsStatic');
    const errorDivStatic = document.getElementById('errorDisplayStatic');
    // const dataFileStaticInput = document.getElementById('dataFileStatic'); // Not directly used for triggering, but good to have if needed for other interactions

    // Simple CSV to JSON parser
    function parseCSV(csvText) {
        const lines = csvText.trim().split('\n');
        if (lines.length < 2) {
            throw new Error("CSV must have a header row and at least one data row.");
        }
        const header = lines[0].split(',').map(h => h.trim());
        const data = [];
        for (let i = 1; i < lines.length; i++) {
            const values = lines[i].split(',');
            if (values.length !== header.length) {
                console.warn(`Skipping line ${i+1}: Number of columns (${values.length}) does not match header (${header.length}). Line: ${lines[i]}`);
                continue;
            }
            const entry = {};
            header.forEach((colName, index) => {
                const value = values[index].trim();
                // Attempt to convert to number if applicable, otherwise keep as string
                entry[colName] = isNaN(Number(value)) || value === '' ? value : Number(value);
            });
            data.push(entry);
        }
        return data;
    }


    // Function to handle the static backtest logic
    function handleStaticBacktest(formData) {
        console.log("Form Data for Static Backtest:", Object.fromEntries(formData.entries()));
        resultsDivStatic.innerHTML = '<h2>Backtest Results (JS):</h2><p>Processing with JavaScript...</p>';
        errorDivStatic.textContent = '';

        const dataFile = formData.get('file');
        const strategy = formData.get('strategy');
        const initialCapital = parseFloat(formData.get('initial_capital'));
        const commissionBps = parseFloat(formData.get('commission_bps'));
        // ... (get other parameters similarly)

        console.log("Selected Strategy:", strategy);
        console.log("Initial Capital:", initialCapital);
        console.log("Commission (bps):", commissionBps);


        if (dataFile && dataFile.size > 0) {
            const reader = new FileReader();
            reader.onload = function(e) {
                const csvContent = e.target.result;
                try {
                    const parsedData = parseCSV(csvContent);
                    console.log("Parsed CSV Data (first 5 entries):", parsedData.slice(0, 5));

                    // Simple High/Low identification
                    const highsLows = identifyHighsLows(parsedData, 5); // Using a small window for simplicity

                    // Simplified strategy: Buy on new high, Sell on new low (very basic)
                    const signals = simpleBreakoutStrategy(parsedData, highsLows);

                    resultsDivStatic.innerHTML = `<h2>Backtest Results (JS):</h2>
                                              <p>CSV file "${dataFile.name}" loaded and parsed successfully.</p>
                                              <p>Strategy: ${strategy}, Initial Capital: ${initialCapital}</p>
                                              <p>Number of data rows: ${parsedData.length}</p>
                                              <p>First data entry: <pre>${JSON.stringify(parsedData[0], null, 2)}</pre></p>
                                              <p>Identified Highs/Lows (sample): <pre>${JSON.stringify(highsLows.slice(0,10), null, 2)}</pre></p>
                                              <p>Generated Signals (sample): <pre>${JSON.stringify(signals.slice(0,10), null, 2)}</pre></p>
                                              <p><b>Note:</b> This is a highly simplified JS backtest. Full logic pending.</p>`;
                } catch (error) {
                    console.error("CSV Parsing Error or Strategy Error:", error);
                    errorDivStatic.textContent = `Error parsing CSV: ${error.message}`;
                    resultsDivStatic.innerHTML = '<h2>Backtest Results (JS):</h2><p>CSV parsing failed.</p>';
                }
            };
            reader.onerror = function(e) {
                console.error("FileReader error:", e);
                errorDivStatic.textContent = 'Error reading file.';
                resultsDivStatic.innerHTML = '<h2>Backtest Results (JS):</h2><p>File reading failed.</p>';
            };
            reader.readAsText(dataFile);
        } else {
            errorDivStatic.textContent = 'No data file selected or file is empty.';
            resultsDivStatic.innerHTML = '<h2>Backtest Results (JS):</h2><p>Please select a valid CSV file.</p>';
        }
    }

    // --- Simplified SMC Concepts & Strategy ---
    function identifyHighsLows(data, window = 3) {
        const points = [];
        if (data.length < window * 2 + 1) return points; // Not enough data for a meaningful window

        for (let i = window; i < data.length - window; i++) {
            let isHigh = true;
            let isLow = true;
            for (let j = 1; j <= window; j++) {
                if (data[i].high < data[i-j].high || data[i].high < data[i+j].high) {
                    isHigh = false;
                }
                if (data[i].low > data[i-j].low || data[i].low > data[i+j].low) {
                    isLow = false;
                }
            }
            if (isHigh) {
                points.push({ index: i, type: 'high', price: data[i].high, timestamp: data[i].timestamp });
            } else if (isLow) {
                points.push({ index: i, type: 'low', price: data[i].low, timestamp: data[i].timestamp });
            }
        }
        return points;
    }

    function simpleBreakoutStrategy(data, highsLows) {
        const signals = [];
        let lastHighPrice = 0;
        let lastLowPrice = Infinity;

        // Find initial high/low from identified points if available
        const initialHighs = highsLows.filter(p => p.type === 'high');
        const initialLows = highsLows.filter(p => p.type === 'low');
        if (initialHighs.length > 0) lastHighPrice = Math.max(...initialHighs.map(h => h.price));
        if (initialLows.length > 0) lastLowPrice = Math.min(...initialLows.map(l => l.price));

        let recentIdentifiedHigh = null;
        let recentIdentifiedLow = null;

        for (let i = 0; i < data.length; i++) {
            // Update recent identified high/low
            const identifiedPoint = highsLows.find(p => p.index === i);
            if(identifiedPoint) {
                if(identifiedPoint.type === 'high') recentIdentifiedHigh = identifiedPoint;
                if(identifiedPoint.type === 'low') recentIdentifiedLow = identifiedPoint;
            }

            // Simplified Breakout Logic:
            // If current bar's high breaks above the most recent *identified* high, consider buy.
            if (recentIdentifiedHigh && data[i].high > recentIdentifiedHigh.price) {
                signals.push({ index: i, type: 'buy_breakout', price: data[i].close, timestamp: data[i].timestamp, reason: `Breakout above high ${recentIdentifiedHigh.price} @ ${recentIdentifiedHigh.timestamp}` });
                if (recentIdentifiedHigh) recentIdentifiedHigh = null; // Reset after breakout
            }
            // If current bar's low breaks below the most recent *identified* low, consider sell.
            else if (recentIdentifiedLow && data[i].low < recentIdentifiedLow.price) {
                signals.push({ index: i, type: 'sell_breakout', price: data[i].close, timestamp: data[i].timestamp, reason: `Breakout below low ${recentIdentifiedLow.price} @ ${recentIdentifiedLow.timestamp}` });
                 if (recentIdentifiedLow) recentIdentifiedLow = null; // Reset after breakout
            }
        }
        return signals;
    }


    if (backtestFormStatic) {
        backtestFormStatic.addEventListener('submit', function (event) {
            event.preventDefault();
            const formData = new FormData(backtestFormStatic);
            handleStaticBacktest(formData);
        });
    } else {
        console.error("Static backtest form (backtestFormStatic) not found!");
    }
});
