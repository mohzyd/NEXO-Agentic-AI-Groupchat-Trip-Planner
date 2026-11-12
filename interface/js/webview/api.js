const API = (() => {
    const $_Listeners = new Map();

    function on(action, callback) {
        if (!$_Listeners.has(action)) {
            $_Listeners.set(action, []);
        }

        $_Listeners.get(action).push(callback);
    }

    function emit(action, data) {
        if ($_Listeners.has(action)) {
            $_Listeners.get(action).forEach(callback => callback(data));
        }
    }

    function pyExecutor(action, dataString) {
        if (!$_Listeners.has(action)) {
            return;
        }
        
        try {
            const data = JSON.parse(dataString);
            $_Listeners.get(action).forEach(callback => callback(data));
        } catch (error) {
            console.error('Error parsing data:', error);
        }
    }

    return {
        on,
        emit,
        pyExecutor
    }
})();

window.API = API;