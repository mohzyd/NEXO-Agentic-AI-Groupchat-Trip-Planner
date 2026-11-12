const detailsModal = (() => {
    const $modal      = document.getElementById('detailsModal');
    const $message    = $modal.querySelector('.error-message');
    const $exitButton = $modal.querySelector('.close-modal');
    const $delButton  = $modal.querySelector('.delete-button');
    const $relButton  = $modal.querySelector('.reload-button');
    const $area       = $modal.querySelector('.options-area');

    let isDisabled = false;
    let isLoading  = false;
    let currentChatId = null;
    let chatData      = null;

    function open() {
        if ($modal.hasAttribute("open")) {
            return;
        }

        $modal.setAttribute("open", "");
    }

    function close() {
        if (!$modal.hasAttribute("open") || isLoading || isDisabled) {
            return;
        }

        $modal.removeAttribute("open");
        setTimeout(() => {
            hideMessage();
            setLoading("delete", false);
            setLoading("reload", false);
            $delButton.hidden = false;
        }, 200);
    }

    function setDisable(status) {
        isDisabled = status;

        if (isDisabled) {
            $exitButton.setAttribute("disabled", "");
            $delButton.setAttribute("disabled", "");
            $relButton.setAttribute("disabled", "");
        } else {
            $exitButton.removeAttribute("disabled");
            $delButton.removeAttribute("disabled");
            $relButton.removeAttribute("disabled");
        }
    }

    function setLoading(type, status) {
        isLoading = status;
        setDisable(isLoading);
        
        let button;
        if (type === "delete") {
            button = $delButton;
        } else if (type === "reload") {
            button = $relButton;
        }

        button.querySelector(".button-loader")
            .hidden = !isLoading;
    }

    function setMessage(message) {
        $message.querySelector('.message')
            .textContent = message;
        $message.hidden  = false;
    }

    function hideMessage() {
        $message.hidden = true;
    }

    async function loadChat(chatId) {
        let chat, found, message;

        try {
            const [chatData, chatFound, responseMessage] = await window.pywebview.api.get_chat_by_id(chatId);
            chat    = chatData;
            found   = chatFound;
            message = responseMessage;
        } catch (error) {
            found = false;
            console.error(error);
            message = "An error occurred while loading chat details.";
        }

        if (!found) {
            $area.innerHTML   = "";
            $delButton.id     = "";
            $delButton.hidden = true;
            currentChatId     = null;
            chatData          = null;
            setMessage(message);
            return;
        }

        if (chat.status.toLowerCase() === "active") {
            $relButton.disabled = true;
        }

        const timeRem   = calculateExpireIn(chat.expire_time || 0);
        currentChatId   = chatId;
        chatData        = chat;
        $area.innerHTML = `
            <div class="option-row">
                <div class="key">Name</div>
                <div class="value">${chat.name}</div>
            </div>
            <div class="option-row">
                <div class="key">Status</div>
                <div class="value">${chat.status}</div>
            </div>
            <div class="option-row">
                <div class="key">Privacy</div>
                <div class="value">${chat.privacy}</div>
            </div>
            ${
                chat.privacy === "private" ? `
                    <div class="option-row">
                        <div class="key">Password</div>
                        <div class="value">${chat.password}</div>
                    </div>` : ""
            }
            <div class="option-row">
                <div class="key">Duration</div>
                <div class="value">${chat.duration === 0 ? "Permanent" : `${chat.duration} minutes`}</div>
            </div>
            <div class="option-row">
                <div class="key">Remaining Time</div>
                <div class="value">${
                    (!chat.lifetime)
                    ? `${timeRem} ${timeRem.includes("Expired") ? "" : "Remaining"}`
                    : "Never"
                }</div>
            </div>
            <div class="option-row">
                <div class="key">Created At</div>
                <div class="value">${chat.created_at}</div>
            </div>
        `;


        $delButton.id = `delete-chat-${chat.id}`;
    }

    $exitButton.addEventListener("click", close);

    $modal.addEventListener("click", (e) => {
        if (e.target === $modal) close();
    });

    $delButton.addEventListener("click", async (e) => {
        e.preventDefault();

        if (e._wait) {
            return;
        }

        e._wait = true;
        setLoading("delete", true);

        let success = false;
        let message = '';

        try {
            const [isSuccess, msg] = await window.pywebview.api.delete_chat(currentChatId);
            
            success = isSuccess;
            message = msg;
            
        } catch (error) {
            console.error(error);
            message = "An error occurred while deleting the chat.";
        }

        e._wait = false;
        if (success) {
            askForRefreshChats();
            setTimeout(() => {
                setLoading("delete", false);
                close();
            }, 500);
        } else {
            setMessage(message);
            setLoading("delete", true);
        }
    });

    $relButton.addEventListener("click", async (e) => {
        e.preventDefault();

        if (e._wait) {
            return;
        }

        e._wait = true;
        setLoading("reload", true);

        let success   = false;
        let message   = '';
        let timestamp = 0;

        if (chatData?.lifetime === false) {
            timestamp = Date.now() + (chatData?.duration * 60 * 1000);
        }

        try {
            const [isSuccess, msg] = await window.pywebview.api.reload_chat(currentChatId, timestamp);
            
            success = isSuccess;
            message = msg;
            
        } catch (error) {
            console.error(error);
            message = "An error occurred while deleting the chat.";
        }

        e._wait = false;
        if (success) {
            askForRefreshChats();
            setTimeout(() => {
                setLoading("reload", false);
                close();
            }, 500);
        } else {
            setMessage(message);
            setLoading("reload", false);
        }
    });

    return {
        open,
        close,
        loadChat
    }
})

function buildDetailsModal() {
    window.detailsModal = detailsModal();
}
