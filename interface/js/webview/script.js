const DataConfig = {}
let documentLoaded = false, webviewLoaded = false;

const loadingToggle = (visibility, message = "Please wait...") => {
    const loading = document.getElementById("loadingModal");
    const text    = document.getElementById("loadingMessage");
    text.textContent = message;
    
    if (visibility) {
        loading.setAttribute("open", "");
    } else {
        loading.removeAttribute("open");
    }
}

const errorMessage = (message = "An unexpected error occurred.") => {
    const modal = document.getElementById("errorModal");
    const text  = document.getElementById("errorMessage");
    text.textContent = message;
    modal.setAttribute("open", "");
}

const getValue = (key, defaultValue) => {
    return DataConfig[key] || defaultValue;
}

const copyTo = (from, to) => {
    for (const key in from) {
        to[key] = from[key];
    }
}

async function loadData() {
    if (!documentLoaded || !webviewLoaded) {
        return;
    }

    try {
        const data = await window.pywebview.api.get_data();
        copyTo(data, DataConfig);
    } catch (error) {
        const errorModal = document.getElementById("errorModal");
        errorModal.style.backdropFilter = "blur(50px)";
        errorModal.querySelector("#closeErrorButton")?.remove();
        console.error("Error loading data:", error);
        errorMessage("Failed to load application data. Please try again." + error);
    }
    loadingToggle(false);

    document.getElementById("closeErrorButton").addEventListener("click" , (e) => {
        e.preventDefault();
        document.getElementById("errorModal").removeAttribute("open");
    });

    document.getElementById("newChat").addEventListener("click", (e) => {
        e.preventDefault();
        const hasRequirement = getValue("hasRequirement", false);

        if (!hasRequirement) {
            window.CloudflaredModal.open();
            return;
        }
    });
}

document.addEventListener("DOMContentLoaded", async () => {
    documentLoaded = true;
    loadData();
});

window.addEventListener("pywebviewready", () => {
    webviewLoaded = true;
    loadData();
});
