export class Diagnostics {
    constructor() {
        this.enabled = true;
    }

    log(message, data = null) {
        if (!this.enabled) return;
        const timestamp = new Date().toISOString();
        const prefix = `[SIM-DIAGNOSTICS ${timestamp}]`;
        if (data) {
            console.log(`${prefix} ${message}`, data);
        } else {
            console.log(`${prefix} ${message}`);
        }
    }

    warn(message, data = null) {
        if (!this.enabled) return;
        const timestamp = new Date().toISOString();
        const prefix = `[SIM-DIAGNOSTICS ${timestamp}]`;
        if (data) {
            console.warn(`${prefix} ${message}`, data);
        } else {
            console.warn(`${prefix} ${message}`);
        }
    }

    error(message, error = null) {
        if (!this.enabled) return;
        const timestamp = new Date().toISOString();
        const prefix = `[SIM-DIAGNOSTICS ${timestamp}]`;
        if (error) {
            console.error(`${prefix} ${message}`, error);
        } else {
            console.error(`${prefix} ${message}`);
        }
    }
}

// Attach a global instance for convenience if not using module imports everywhere
window.Diag = new Diagnostics();
