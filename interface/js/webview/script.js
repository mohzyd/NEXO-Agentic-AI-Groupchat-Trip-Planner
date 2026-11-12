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

const copyToClipboard = async (text) => {
    let isCopied     = false;
    let errorMessage = "";

    try {
        const [copied, message] = await window.pywebview.api.copy_text_to_clipboard(text);
        isCopied                = copied;
        errorMessage            = message;
    } catch (error) {
        errorMessage = error?.message || error || "An unknown error occurred. Please try again.";
    }

    return [isCopied, errorMessage];
}

window.copyURL = async (button, url) => {
    if (button._timeout) {
        return;
    }

    button._timeout   = true;
    [copied, message] = await copyToClipboard(url);
    
    if (copied) {
        button.textContent = "Copied!";
        setTimeout(() => {
            button.textContent = "Copy";
            button._timeout = false;
        }, 2000);
    } else {
        errorMessage(`Failed to copy URL: ${message}`);
        button._timeout = false;
    }
};

const calculateExpireIn = (timestamp) => {
    const now        = new Date();
    const expireTime = new Date(timestamp);
    const diff       = expireTime - now;
    
    if (diff <= 0) {
        return "Expired";
    }

    const totalSeconds = Math.floor(diff / 1000);
    const seconds      = totalSeconds % 60;
    const totalMinutes = Math.floor(totalSeconds / 60);
    const minutes      = totalMinutes % 60;
    const hours        = Math.floor(totalMinutes / 60);

    if (totalMinutes < 1) {
        return `${seconds} Seconds`;
    }

    if (hours < 1) {
        return `${minutes} Minutes`;
    }

    return `${hours} Hours`;
}

const loadDetails = async (chatId) => {
    loadingToggle(true, "Loading chat details...");
    await window.detailsModal.loadChat(chatId);
    window.detailsModal.open();
    loadingToggle(false);
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

            const status = !chat.lifetime && calculateExpireIn(chat.expire_time) === "Expired"
                ? "Inactive"
                : chat.status.toLowerCase() === "active" ? "Active" : "Inactive";

            HTMLText += `
                <div class="chat">
                    <div class="more-details-line" onclick="loadDetails('${chat.chat_id}')"></div>
                    <div class="short-container">
                        <span>${chat.short_name}</span>
                    </div>
                    <div class="name">
                        <span>${chat.name}</span>
                    </div>
                    <div class="sep-line"></div>
                    <div class="row">
                        <div class="status ${status.toLowerCase()}">
                            <div class="dot"></div>
                            <div class="text">${status}</div>
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
                        <button class="copy" onclick="copyURL(this, '${chat.url}')">Copy</button>
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

            if (Math.floor(Math.random() * 2) == 0) {
                loadChats(getValue("chats", []));
            } else {
                askForRefreshChats();
            }

        }, Math.floor(Math.random() * 5000) + 3000);
    }

    chatsElement.innerHTML = HTMLText;
    inLoadingChats         = false;
}

const askForRefreshChats = async () => {
    try {
        const chats = await window.pywebview.api.load_chats();
        
        if (chats.length === 0) {
            setValue("chats", []);
            loadChats([]);
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
                setValue("chats", chats);
                loadChats(chats);
            }

            refreshingMethod();
            return;
        }

        setValue("chats", chats);
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
        buildDetailsModal();
        buildCloudflaredModal();
        buildNewChatModal();
    } catch (error) {
        const errorModal                = document.getElementById("errorModal");
        errorModal.style.backdropFilter = "blur(50px)";
        errorModal.querySelector("#closeErrorButton")?.remove();
        console.error("Error loading data:", error);
        errorMessage("Failed to load application data. Please try again." + error);
    }

    loadChats(getValue("chats", []));

    const pathContainer = document.getElementById("cloudflaredPath");
    if (pathContainer) {
        const targetName          = getValue("appDataFileName", "undefined");
        let newText               = pathContainer.textContent.replace("{{appDataFileName}}", targetName);
        newText                   = newText.replace("{{cloudflaredServiceName}}", getValue("cloudflaredServiceName", "cloudflare_tunnel_no.exe"));
        pathContainer.textContent = newText;
    }

    loadingToggle(false);

    document.getElementById("closeErrorButton").addEventListener("click" , (e) => {
        e.preventDefault();
        document.getElementById("errorModal").removeAttribute("open");
    });

    document.getElementById("newChat").addEventListener("click", async (e) => {
        e.preventDefault();
        if (e.__should_wait) return;
        e.__should_wait = true;
        
        const response       = await window.pywebview.api.is_cloudservice_installed();
        const hasRequirement = response?.status === true;

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

window.addEventListener("contextmenu", (e) => {
    e.preventDefault();
    e.stopPropagation();
});