const CloudflaredModal = (() => {
    const modal = document.getElementById("cloudflaredModal");

    const options       = modal.querySelector("#installationOptions");
    const automaticView = modal.querySelector(".automatic-view");
    const manualView    = modal.querySelector(".manual-view");

    const progressSection    = modal.querySelector("#progressSection");
    const progressFill       = modal.querySelector("#progressFill");
    const progressPercentage = modal.querySelector("#progressPercentage");
    const progressTitle      = modal.querySelector("#progressTitle");
    const progressSubtitle   = modal.querySelector("#progressSubtitle");
    const progressStatus     = modal.querySelector("#progressStatus");
    const progressSize       = modal.querySelector("#progressSize");

    const result             = modal.querySelector("#installationResult");
    const resultIcon         = result.querySelector(".result-icon");
    const resultTitle        = result.querySelector(".result-title");
    const resultText         = result.querySelector(".result-text");

    const downloadButton     = modal.querySelector("#installButton")
    const retryButton        = modal.querySelector(".retry-button");
    const doneButton         = modal.querySelector(".done-button");

    const verifyButton       = modal.querySelector(".verify-button");
    const manualResult       = modal.querySelector(".manual-result");
    const copyPathButton     = modal.querySelector(".copy-path-button");

    let isInstalling = false;
    let isInstalled  = false;
    let blocked      = false;

    const icons = {
        success: `
            <svg viewBox="0 0 24 24" fill="none">
                <path d="M20 6L9 17L4 12"
                    stroke="currentColor" stroke-width="2"
                    stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
        `,

        error: `
            <svg viewBox="0 0 24 24" fill="none">
                <circle cx="12" cy="12" r="9"
                    stroke="currentColor" stroke-width="1.8"/>
                <path d="M12 7V13M12 16.5V16.51"
                    stroke="currentColor" stroke-width="2"
                    stroke-linecap="round"/>
            </svg>
        `
    };

    function open() {
        modal.hidden = false;
        modal.setAttribute("open", "");
        showOptions();
    }

    function close() {
        if (isInstalling || modal.wait) return;
        modal.wait = true;

        modal.removeAttribute("open");
        setTimeout(() => {
            modal.hidden = true;
            modal.wait   = false;
        }, 200);
    }

    function showOptions() {
        options.hidden             = false;
        automaticView.hidden       = true;
        manualView.hidden          = true;

        if (!isInstalled && !isInstalling) {
            result.hidden          = true;
            retryButton.hidden     = true;
            doneButton.hidden      = true;
            downloadButton.hidden  = false;
            progressSection.hidden = true;
        }
    }

    function showAutomatic() {
        options.hidden        = true;
        automaticView.hidden  = false;
        manualView.hidden     = true;
    }

    function showManual() {
        options.hidden       = true;
        automaticView.hidden = true;
        manualView.hidden    = false;

        manualResult.hidden      = true;
        manualResult.className   = "manual-result";
        manualResult.textContent = "";
        setVerifying(false);
    }

    function resetProgress() {
        updateProgress(0);

        progressTitle.textContent    = "Preparing download...";
        progressSubtitle.textContent = "Please wait while we set things up.";
        progressStatus.textContent   = "Waiting to start";
        progressSize.textContent     = "";

        result.hidden      = true;
        retryButton.hidden = true;
        doneButton.hidden  = true;
    }

    function updateProgress(percentage, details = {}) {

        const value = Math.max(0, Math.min(100, Number(percentage) || 0));

        progressFill.style.width = `${value}%`;
        progressPercentage.textContent = `${Math.round(value)}%`;

        if (details.title !== undefined) {
            progressTitle.textContent = details.title;
        }

        if (details.subtitle !== undefined) {
            progressSubtitle.textContent = details.subtitle;
        }

        if (details.status !== undefined) {
            progressStatus.textContent = details.status;
        }

        if (details.size !== undefined) {
            progressSize.textContent = details.size;
        }
    }

    function showResult(type, title, text) {
        const validTypes = ["success", "error"];
        if (!validTypes.includes(type)) return;

        result.className        = `installation-result ${type}`;
        resultIcon.innerHTML    = icons[type];
        resultTitle.textContent = title;
        resultText.textContent  = text;
        result.hidden           = false;
    }

    async function startInstallation() {
        if (isInstalling) return;

        showAutomatic();
        resetProgress();

        isInstalling = true;
        setCloseDisabled(true);

        downloadButton.hidden = true;
        retryButton.hidden    = true;
        doneButton.hidden     = true;
        result.hidden         = true;

        progressTitle.textContent    = "Starting installation...";
        progressSubtitle.textContent = "Initializing the Cloudflared setup.";
        progressStatus.textContent   = "Initializing";

        let isDownloadingStarted = false;
        let errorMessage         = "";
        
        try {
            const [rStatus, rMessage] = await window.pywebview.api.start_cloudservice_download();
            isDownloadingStarted      = rStatus;
            errorMessage              = rMessage;
        } catch (error) {
            errorMessage = error?.message || error || "An unknown error occurred. Please try again.";
        }

        if (!isDownloadingStarted) {
            failInstallation(errorMessage);
        }

        progressSection.hidden = false;
    }

    function completeInstallation() {
        isInstalling = false;
        isInstalled  = true;
        setCloseDisabled(false);

        updateProgress(100, {
            title:    "Installation completed!",
            subtitle: "Cloudflared is ready to use.",
            status:   "Completed"
        });

        showResult(
            "success",
            "Successfully installed",
            "Cloudflared has been installed and verified successfully."
        );

        doneButton.hidden  = false;
        retryButton.hidden = true;
    }


    function failInstallation(error) {
        isInstalling = false;
        setCloseDisabled(false);

        progressTitle.textContent    = "Installation failed";
        progressSubtitle.textContent = "Something prevented Cloudflared from being installed.";
        progressStatus.textContent   = "Failed";

        showResult(
            "error",
            "Unable to install Cloudflared",
            error || "An unexpected error occurred during installation."
        );

        retryButton.hidden = false;
        doneButton.hidden  = true;
    }

    function setVerifying(state) {
        verifyButton.disabled = state;

        verifyButton.classList.toggle("loading", state);
        verifyButton.querySelector(".verify-text").textContent = state
            ? "Checking..."
            : "Verify installation";
    }

    async function verifyInstallation() {
        if (blocked) return;
        blocked = true;
        setVerifying(true);

        isInstalled      = false;
        let errorMessage = "";

        try {
            const data   = await window.pywebview.api.is_cloudservice_installed();
            isInstalled  = data.status;
            errorMessage = data.message;
        } catch (error) {
            errorMessage = error?.message || error || "An unknown error occurred. Please try again.";
        }

        setVerifying(false);

        manualResult.className   = `manual-result ${isInstalled ? "success" : "error"}`;
        manualResult.textContent = isInstalled
            ? "Cloudflared was detected successfully and is ready to use."
            : (errorMessage || "Cloudflared could not be detected. Check its location and try again.");

        manualResult.hidden = false;

        if (!isInstalled) return;
        
        setValue("hasRequirement", true);
        setCloseDisabled(true);
        setTimeout(() => {
            blocked = false;
            close();
            try {
                window.NewChatModal.open()
            } catch (error) {}
            setCloseDisabled(false);
        }, 1000);
    }

    modal.querySelectorAll("[data-installation]").forEach(button => {

        button.addEventListener("click", () => {

            if (button.dataset.installation === "automatic") {
                showAutomatic();
            }

            if (button.dataset.installation === "manual") {
                showManual();
            }

        });
    });


    modal.querySelectorAll(".back-button").forEach(button => {
        button.addEventListener("click", () => {
            if (!isInstalling && !blocked) showOptions();
        });
    });


    modal.querySelector(".close-modal").addEventListener("click", close);

    modal.addEventListener("click", event => {
        if (event.target === modal) close();
    });

    document.addEventListener("keydown", event => {
        if (event.key === "Escape" && !modal.hidden) {
            close();
        }
    });

    downloadButton.addEventListener("click", (e) => {
        downloadButton.hidden = true;
        startInstallation();
    });


    retryButton.addEventListener("click", startInstallation);

    doneButton.addEventListener("click", () => {

        if (!isInstalled) return;

        try {
            window.NewChatModal.open();
        } catch(error) {}

        close();
    });

    copyPathButton.addEventListener("click", async () => {
        if (copyPathButton.wait) {
            return;
        }

        copyPathButton.wait = true;
        const path          = modal.querySelector("#cloudflaredPath").textContent.trim();

        const [isCopied, errorMessage] = await copyToClipboard(path);

        if (isCopied) {
            copyPathButton.title       = "Copied!";
            copyPathButton.style.color = "hsl(130 50% 35%)";
            manualResult.className     = "manual-result success";
            manualResult.textContent   = "Copied!";
            manualResult.hidden        = false;

            window.setTimeout(() => {
                copyPathButton.title       = "Copy path";
                copyPathButton.style.color = "";
                copyPathButton.wait        = false;
                manualResult.hidden        = true;
            }, 1200);
        } else {
            manualResult.className   = "manual-result error";
            manualResult.textContent = "Unable to copy the path. Please copy it manually. " + errorMessage;
            manualResult.hidden      = false;
            copyPathButton.wait      = false;
            console.error(`Failed to copy Cloudflared path: ${errorMessage}`);
        }
    });

    verifyButton.addEventListener("click", verifyInstallation);

    function setCloseDisabled(disabled) {
        modal.querySelector(".close-modal").disabled = disabled;
    }

    return {
        open,
        close,
        updateProgress,
        completeInstallation,
        failInstallation
    };

});

function buildCloudflaredModal() {
    window.CloudflaredModal = CloudflaredModal();
}

window.API.on("downloadCloudflaredUpdate", (data) => {
    const { downloaded, total } = data;
    let progress = 100;

    if (total > 0) {
        progress = Math.round((downloaded / total) * 100);
    }

    window.CloudflaredModal.updateProgress(progress);
});

window.API.on("downloadCloudflaredComplete", (data) => {
    const { success, reason } = data;

    if (success) {
        window.CloudflaredModal.completeInstallation();
        setValue("hasRequirement", true);
        return;
    }

    window.CloudflaredModal.failInstallation(reason || "Failed to download Cloudflared");
});