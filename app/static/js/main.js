document.addEventListener("DOMContentLoaded", () => {
    console.log("main.js loaded ✅");

    const statusBar = document.getElementById('status-bar');
    const statusMessage = document.getElementById('status-message');
    
    // Nifty 50 identifier used in the backend payload
    const NIFTY_50_PAYLOAD_KEY = 'Nifty 50';

    /**
     * Helper function to update text content of an element with formatting and color logic.
     * @param {string} id - The element ID.
     * @param {number|string} value - The value to display.
     * @param {boolean} isPrice - If true, formats to 2 decimal places.
     * @param {boolean} isPnL - If true, applies PnL color logic (Green/Red/Yellow).
     */
    function updateText(id, value, isPrice = false, isPnL = false) {
        const el = document.getElementById(id);
        if (el) {
            if (value !== undefined && value !== null) {
                let formattedValue = value;
                
                if (isPnL) {
                    // PnL Color Logic
                    el.classList.remove('text-green-500', 'text-red-500', 'text-yellow-300');
                    const numValue = parseFloat(value);
                    if (!isNaN(numValue)) {
                        if (numValue > 0) {
                            el.classList.add('text-green-500');
                        } else if (numValue < 0) {
                            el.classList.add('text-red-500');
                        } else {
                            el.classList.add('text-yellow-300'); // Neutral PnL color
                        }
                        formattedValue = numValue.toFixed(2); // PnL is always 2 decimal places
                    } else {
                         formattedValue = '---.--';
                    }
                } else if (isPrice) {
                    const numValue = parseFloat(value);
                    formattedValue = !isNaN(numValue) ? numValue.toFixed(2) : '---.--';
                }
                
                el.innerText = formattedValue;
            } else {
                el.innerText = isPrice || isPnL ? '---.--' : '--';
            }
        }
    }

    /**
     * Main function to update the entire dashboard based on the live data payload.
     * @param {object} data - The 'market_state' object from task_order_manager.py.
     */
    function updateDashboard(data) {
        
        // --- 1. OVERALL TREND SIGNAL ---
        const trendSignal = data.overall_market_trend || "NEUTRAL";
        
        document.getElementById('trend-signal-call_buy').classList.toggle('hidden', trendSignal !== 'CALL BUY');
        document.getElementById('trend-signal-put_buy').classList.toggle('hidden', trendSignal !== 'PUT BUY');
        document.getElementById('overall-trend-neutral').classList.toggle('hidden', trendSignal === 'CALL BUY' || trendSignal === 'PUT BUY');


        // --- 2. NIFTY 50 DATA ---
        // Payload structure: data.indices_data['Nifty 50']
        const niftyData = data.indices_data?.[NIFTY_50_PAYLOAD_KEY];

        if (niftyData) {
            const idPrefix = 'nifty_50';
            
            // Nifty LTP and calculated signal
            updateText(`${idPrefix}-ltp`, niftyData.ltp, true); 
            updateText(`${idPrefix}-signal`, niftyData.signal); 
            
            // SMA values
            updateText(`${idPrefix}-sma10`, niftyData.sma_10, true);
            updateText(`${idPrefix}-sma25`, niftyData.sma_25, true);
            updateText(`${idPrefix}-sma50`, niftyData.sma_50, true);
            updateText(`${idPrefix}-sma100`, niftyData.sma_100, true);
        }
        
        // --- 3. ATM OPTIONS METADATA ---
        // Payload structure: data.final_trade_instruments
        const optionMeta = data.final_trade_instruments;

        if (optionMeta) {
            const strike = optionMeta.atm_strike;
            const expiry = optionMeta.expiry_date;
            
            // Update display elements
            updateText('atm-call-strike', `Strike ${strike}`);
            updateText('atm-put-strike', `Strike ${strike}`);
            updateText('atm-expiry-date', expiry);

            // Set HIDDEN instrument keys for trading/data fetch
            const atmCallKeyEl = document.getElementById('atm-call-key');
            const atmPutKeyEl = document.getElementById('atm-put-key');
            if (atmCallKeyEl) atmCallKeyEl.innerText = optionMeta.atm_call?.instrument_key || '';
            if (atmPutKeyEl) atmPutKeyEl.innerText = optionMeta.atm_put?.instrument_key || '';
        }
        
        // --- 4. ACTIVE TRADE AND PNL ---
        // Payload structure: data.active_trade
        const activeTrade = data.active_trade;
        const activeTradeSection = document.getElementById('active-trade-section');

        if (activeTrade && activeTrade.instrument_token) {
            activeTradeSection.classList.remove('hidden'); 

            updateText('active-trade-type', activeTrade.type || '--');
            updateText('active-trade-entry-price', activeTrade.entry_price, true);
            updateText('active-trade-instrument', activeTrade.type === 'CALL' ? `CALL ${optionMeta?.atm_strike}` : `PUT ${optionMeta?.atm_strike}`);

            // PnL/LTP data must be sent by the backend's manage_orders task 
            const livePnl = activeTrade.live_pnl;             
            
            updateText('live-pnl', livePnl, false, true); // PnL formatting
            
        } else {
            activeTradeSection.classList.add('hidden');
        }
    }
    
    // ------------------------------------------------------------------
    // --- SOCKET.IO CONNECTION AND HANDLERS ---
    // ------------------------------------------------------------------

    // 1. Initial Data Fetch (Optional, but good for page load)
    if (document.getElementById('status-bar')) {
        fetch('/api/get-dashboard-state') // You must implement this Flask route
            .then(response => response.json())
            .then(initialData => {
                if (initialData) { updateDashboard(initialData); }
            })
            .catch(error => console.error("Error fetching initial dashboard state:", error));
    }

    // 2. Socket.IO Setup
    const socket = io("https://algo4all.in", {
    transports: ["websocket", "polling"]
});




    socket.on('connect', () => {
        console.log('WebSocket connection established.');
        if (statusMessage) {
            statusMessage.textContent = 'Live connection established. Monitoring market...';
            statusBar.className = 'p-3 rounded-xl shadow-lg text-center font-bold bg-blue-100 text-blue-800 border border-blue-400 transition-all duration-300';
        }
    });

    socket.on('market_update', (liveData) => {
        // This is the primary data stream from task_order_manager.py
        if (document.getElementById('status-bar')) {
            updateDashboard(liveData);
        }
    });

    socket.on('trade_notification', (data) => {
        console.log('Received trade_notification:', data);
        alert(`🔔 TRADE ALERT 🔔\n\n${data.message}`);
        if (statusMessage) {
            statusMessage.textContent = 'Trade Placed! Now managing position.';
            statusBar.className = 'p-3 rounded-xl shadow-lg text-center font-bold bg-green-100 text-green-800 border border-green-400 transition-all duration-300';
        }
    });

    socket.on('disconnect', () => {
        console.error('WebSocket connection lost.');
        if (statusMessage) {
            statusMessage.textContent = 'Connection Lost! Attempting to reconnect...';
            statusBar.className = 'p-3 rounded-xl shadow-lg text-center font-bold bg-red-100 text-red-800 border border-red-400 transition-all duration-300';
        }
    });
    
    socket.on('connect_error', (error) => {
        console.error('Socket.IO Connection Error:', error);
    });

    // 3. EMERGENCY SQUARE OFF Form Handling
    const squareOffForm = document.getElementById('square-off-form');
    if (squareOffForm) {
        squareOffForm.addEventListener('submit', (event) => {
             event.preventDefault(); // Prevent default form submission
             const userIsSure = window.confirm("Are you sure you want to perform an EMERGENCY SQUARE OFF? This action cannot be undone.");
             if (userIsSure) {
                const submitButton = squareOffForm.querySelector('button[type="submit"]');
                if (submitButton) {
                    submitButton.disabled = true;
                    submitButton.textContent = "Processing...";
                }
                // NOTE: Implement a dedicated Flask route /api/square-off 
                // that calls the order manager task's square-off logic.
                fetch('/api/square-off', { method: 'POST' }) 
                    .then(response => response.json())
                    .then(data => {
                        alert(data.message || "Square-off complete.");
                        submitButton.disabled = false;
                        submitButton.textContent = "EMERGENCY SQUARE OFF";
                    })
                    .catch(error => {
                        console.error("Square-off failed:", error);
                        alert("Square-off failed. Check server logs.");
                        submitButton.disabled = false;
                        submitButton.textContent = "EMERGENCY SQUARE OFF";
                    });
            }
        });
    }

    // 4. Logout Link Handling (Unmodified)
    const logoutLink = document.getElementById('logout-link');
    if (logoutLink) {
        logoutLink.addEventListener('click', function(event) {
            event.preventDefault();
            const userIsSure = window.confirm("Are you sure you want to log out?");
            if (userIsSure) {
                const body = document.querySelector('body');
                if(body) {
                    body.innerHTML = '<div style="display:flex; justify-content:center; align-items:center; height:100vh; font-family:sans-serif; font-size:1.5rem; color:#333;">Logging out...</div>';
                }
                window.location.href = this.href;
            }
        });
    }
});