const DataConfig = {}
let documentLoaded = false, webviewLoaded = false;
let refreshChatsInterval = null, inLoadingChats = false;

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

const setValue = (key, value) => {
    DataConfig[key] = value;
}

const copyTo = (from, to) => {
    for (const key in from) {
        to[key] = from[key];
    }
}

// Should return a string in format like "21 Minutes" or "Hour" or "2 Hours"
const calculateExpireIn = (timestamp) => {
    const now        = new Date();
    const expireTime = new Date(timestamp);
    const diff       = expireTime - now;
    const minutes    = Math.floor(diff / 60000);
    
    if (minutes < 60) {
        return `${minutes} Minutes`;
    }
    
    const hours = Math.floor(minutes / 60);
    if (hours === 1) {
        return "Hour";
    }
    
    return `${hours} Hours`;
}

const loadChats = (chats) => {
    if (inLoadingChats) return;

    if (refreshChatsInterval) {
        clearInterval(refreshChatsInterval);
        refreshChatsInterval = null;
    }

    inLoadingChats         = true;
    const chatsElement     = document.querySelector(".chats .area");
    chatsElement.innerHTML = "";
    let HTMLText           = ``;

    for (let M = 0; M < 4; M++) {
        try {
            
            if (!Array.isArray(chats)) {
                throw new Error(`Chats is not array. Skip ${M + 1}/4`);
            }

            const chat = chats[M];
            if (!chat) {
                throw new Error(`Chat ${M + 1} not found. Skip ${M + 1}/4`);
            }

            HTMLText += `
                <div class="chat">
                    <div class="more-details-line" id="CHAT-${chat.id}"></div>
                    <div class="short-container">
                        <span>${chat.short_name}</span>
                    </div>
                    <div class="name">
                        <span>${chat.name}</span>
                    </div>
                    <div class="sep-line"></div>
                    <div class="row">
                        <div class="status ${chat.status.toLowerCase() === "active" ? "active" : "inactive"}">
                            <div class="dot"></div>
                            <div class="text">${chat.status}</div>
                        </div>
                        <div class="expire-in">
                            ${
                                (!chat.lifetime)
                                 ? calculateExpireIn(chat.expire_time)
                                 : "Never"
                            }
                        </div>
                    </div>
                    <div class="share-link">
                        <span class="link">${chat.url}</span>
                        <button class="copy" onclick="copyToClipboard('${chat.url}')">Copy</button>
                    </div>
                </div>
            `;

        } catch (error) {
            console.error(`Error loading chat ${M + 1}:`, error, "Will replace it with ghost chat");
            HTMLText += `
                <div class="chat ghost"></div>
            `;
        }
    }

    if (Array.isArray(chats) && chats.length > 0) {
        refreshChatsInterval = setInterval(() => {
            // 50% chance to refresh. To reduce refreshing source usage.
            if (Math.floor(Math.random() * 2) == 1) return;

            loadChats(getValue("chats", []));
        }, Math.floor(Math.random() * 5000) + 3000);
    }

    chatsElement.innerHTML = HTMLText;
    inLoadingChats         = false;
}

const askForRefreshChats = async () => {
    try {
        const chats = await window.pywebview.api.load_chats();
        
        if (chats.length === 0) {
            return;
        }

        // In case we recived chats data in the same time of reloading chats, we just will wait and try loading new data again until previous loading ends.
        if (inLoadingChats) {
            const randomKey = Math.random().toString(36).substring(2, 15);
            askForRefreshChats[`__retry_count_${randomKey}`] = 0; 

            const refreshingMethod = () => {
                if (inLoadingChats) {
                    askForRefreshChats[`__retry_count_${randomKey}`]++;
                    setTimeout(refreshingMethod, Math.min(5000, Math.pow(2, askForRefreshChats[`__retry_count_${randomKey}`]) + 50));
                    return;
                }

                delete askForRefreshChats[`__retry_count_${randomKey}`]; // Clean up the reference
                loadChats(chats);
            }

            refreshingMethod();
            return;
        }

        loadChats(chats);
    } catch (error) {/* Just passing, no need to handle error */ }
}

async function loadData() {
    if (!documentLoaded || !webviewLoaded) {
        return;
    }

    try {
        const data = await window.pywebview.api.get_data();
        copyTo(data, DataConfig);
    } catch (error) {
        const errorModal                = document.getElementById("errorModal");
        errorModal.style.backdropFilter = "blur(50px)";
        errorModal.querySelector("#closeErrorButton")?.remove();
        console.error("Error loading data:", error);
        errorMessage("Failed to load application data. Please try again." + error);
    }

    loadChats(getValue("chats", []));
    loadingToggle(false);

    askForRefreshChats();
    askForRefreshChats();

    const pathContainer = document.getElementById("cloudflaredPath");
    if (pathContainer) {
        const targetName          = getValue("appDataFileName", "undefined");
        let newText               = pathContainer.textContent.replace("{{appDataFileName}}", targetName);
        newText                   = newText.replace("{{cloudflaredServiceName}}", getValue("cloudflaredServiceName", "cloudflare_tunnel_no.exe"));
        pathContainer.textContent = newText;
    }

    document.getElementById("closeErrorButton").addEventListener("click" , (e) => {
        e.preventDefault();
        document.getElementById("errorModal").removeAttribute("open");
    });

    document.getElementById("newChat").addEventListener("click", async (e) => {
        e.preventDefault();
        if (e.__should_wait) return;
        e.__should_wait = true;
        
        const hasRequirement = getValue("hasRequirement", false);

        if (!hasRequirement) {
            window.CloudflaredModal.open();
            e.__should_wait = false;
            return;
        }

        // checking if can create more chats
        try {
            const canCreate = await window.pywebview.api.can_create_chat();
            
            if (!canCreate) {
                errorMessage("You have reached the maximum number of chats. Please delete an existing chat to create a new one.");
                e.__should_wait = false;
                return;
            }

        } catch (error) {
            console.error("Error checking if can create chat:", error);
            errorMessage("Failed to check if can create chat. Please try again.");
            e.__should_wait = false;
            return;
        }

        window.NewChatModal.open();
        e.__should_wait = false;
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
