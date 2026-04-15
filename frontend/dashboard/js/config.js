const CONFIG = {
    api: {
        baseUrl: 'https://dev.plotra.eu/api/v2',
        apiBaseUrl: '/api/v2',
        timeout: 30000,
        retryAttempts: 3,
        retryDelay: 1000
    },
    
    gps: {
        enableHighAccuracy: true,
        timeout: 30000,
        maximumAge: 60000,
        minAccuracy: 20,
        minPoints: 4,
        recordingInterval: 2000
    },
    
    offline: {
        enabled: true,
        maxQueuedRequests: 100,
        syncOnReconnect: true
    },
    
    map: {
        defaultCenter: [0.0236, 37.9062],
        defaultZoom: 6,
        parcelZoom: 15,
        tileUrl: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png'
    },
    
    session: {
        tokenKey: 'plotra_token',
        userKey: 'plotra_user',
        refreshBeforeExpiry: 5 * 60 * 1000
    },
    
    ui: {
        animations: true,
        toastDuration: 3000,
        pageTransition: 200
    }
};

const ENV = {
    isProduction: window.location.hostname !== 'localhost',
    isMobile: /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent),
    hasGPS: 'geolocation' in navigator,
    hasNetwork: 'onLine' in navigator,
    serviceWorkerSupported: 'serviceWorker' in navigator
};

window.PLOTRA_CONFIG = CONFIG;
window.PLOTRA_ENV = ENV;
window.apiBaseUrl = CONFIG.api.baseUrl;

console.log('✅ Config loaded:', {
    baseUrl: window.apiBaseUrl,
    isProduction: ENV.isProduction,
    hasGPS: ENV.hasGPS
});
