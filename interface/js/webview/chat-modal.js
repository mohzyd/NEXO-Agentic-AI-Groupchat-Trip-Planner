const NewChatModal = (() => {

    const modal         = document.getElementById("newChatModal");
    const form          = document.getElementById("newChatForm");

    const chatName      = document.getElementById("chatName");
    const privacy       = document.getElementById("chatPrivacy");
    const passwordGroup = document.getElementById("passwordGroup");
    const password      = document.getElementById("chatPassword");

    const durationOptions = document.querySelectorAll(
        "#durationOptions .duration-option"
    );

    const message      = document.getElementById("chatMessage");
    const messageTitle = message.querySelector(".message-title");
    const messageText  = message.querySelector(".message-text");
    const messageIcon  = message.querySelector(".message-icon");
    const createButton = form.querySelector(".create-button");

    let selectedDuration = null;
    let isLoading        = false;

    const icons = {
        warning: `
            <svg viewBox="0 0 24 24" fill="none">
                <path d="M12 8V13M12 16.5V16.51"
                    stroke="currentColor" stroke-width="2"
                    stroke-linecap="round"/>
                <path d="M10.3 3.86L2.7 17.05A2 2 0 0 0 4.43 20H19.57A2 2 0 0 0 21.3 17.05L13.7 3.86A2 2 0 0 0 10.3 3.86Z"
                    stroke="currentColor" stroke-width="1.7"/>
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
        `,

        success: `
            <svg viewBox="0 0 24 24" fill="none">
                <path d="M20 6L9 17L4 12"
                    stroke="currentColor" stroke-width="2"
                    stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
        `,

        info: `
            <svg viewBox="0 0 24 24" fill="none">
                <circle cx="12" cy="12" r="9"
                    stroke="currentColor" stroke-width="1.8"/>
                <path d="M12 11V16M12 8V8.01"
                    stroke="currentColor" stroke-width="2"
                    stroke-linecap="round"/>
            </svg>
        `
    };

    function open() {
        if (modal.hasAttribute("open")) {
            return;
        }

        modal.setAttribute("open", '');
        setTimeout(() => {
            chatName.focus();
        }, 100);
    }

    function close() {
        if (isLoading || !modal.hasAttribute("open")) {
            return;
        }

        modal.removeAttribute("open");
        chatName.value       = "";
        privacy.value        = "public";
        passwordGroup.hidden = true;
        password.value       = "";
        password.required    = false;
        hideMessage();
    }

    privacy.addEventListener("change", () => {
        const requiresPassword = (privacy.value === "private");

        passwordGroup.hidden = !requiresPassword;
        password.required    = requiresPassword;

        if (!requiresPassword) {
            password.value = "";
        }
    });

    durationOptions.forEach(option => {
        option.addEventListener("click", () => {
            const duration = Number(option.dataset.duration);

            // Clicking the selected option to deselect it.
            if (selectedDuration === duration) {
                selectedDuration = null;
                option.classList.remove("active");
            } else {
                durationOptions.forEach(item => {
                    item.classList.remove("active");
                });

                selectedDuration = duration;
                option.classList.add("active");
            }
        });
    });

    // Appears a helpful message to the user.
    function showMessage(type, text, title = null) {
        const validTypes = ["warning", "error", "success", "info"];
        
        if (!validTypes.includes(type)) {
            type = "info";
        }

        const defaultTitles = {
            warning: "Warning",
            error:   "Something went wrong",
            success: "Success",
            info:    "Information"
        };

        message.className        = `warning-container ${type}`;
        messageTitle.textContent = title || defaultTitles[type];
        messageText.textContent  = text;
        messageIcon.innerHTML    = icons[type];
        message.hidden           = false;
    }

    function hideMessage() {
        message.hidden = true;
    }

    function setLoading(state) {
        isLoading = state;

        createButton.classList.toggle("loading", state);
        createButton.disabled = state;
        createButton.querySelector(".button-text").textContent = state
            ? "Creating..."
            : "Create chat";

        modal.querySelector(".close-modal").disabled = state;
    }

    function getShortName(name) {
        name = String(name);
        const words = name.split(" ");
        if (words.length > 1) {
            return (words.map(word => word[0]).join("")).toUpperCase();
        }

        const middleChar = Math.floor(name.length / 2);
        return (name.substring(0, 1) + name.substring(middleChar, middleChar + 1)).toUpperCase();
    }

    createButton.addEventListener("click", async event => {
        event.preventDefault();

        if (isLoading) return;
        setLoading(true);
        hideMessage();

        const name      = chatName.value.trim();
        const shortName = getShortName(name);

        const data = {
            chat_name:  name,
            short_name: shortName,
            privacy:    privacy.value,
            password:   privacy.value === "private"
                        ? password.value.trim()
                        : null,
            lifetime:   selectedDuration ? false : true,
            expire_time: selectedDuration 
                        ? Date.now() + (selectedDuration * 60 * 1000)
                        : null,
            duration:   selectedDuration ? selectedDuration : 0,
            created_at: new Date().toLocaleString("en-US", {
                dateStyle: "medium",
                timeStyle: "short",
                hour12:    true
            })
        };

        if (!data.chat_name) {
            showMessage("warning", "Please enter a chat name.");
            setLoading(false);
            return;
        }

        if (data.privacy === "private" && data.password.length < 6) {
            showMessage(
                "warning",
                "Your password must contain at least 6 characters."
            );
            setLoading(false);
            return;
        }

        let isCreated    = false;
        let errorMessage = "";

        try {
            const [status, message] = await window.pywebview.api.create_new_chat(data);
            isCreated = status; errorMessage = message;
        } catch (error) {
            errorMessage = error.message || error || "An unknown error occurred.";
        }

        if (!isCreated) {
            showMessage("error", errorMessage);
            setLoading(false);
            return;
        }

        showMessage("success", "Chat created successfully!");
        askForRefreshChats();
        setTimeout(() => {
            setLoading(false);
            close();
        }, 600);
    });

    modal.querySelector(".close-modal").addEventListener("click", close);
    modal.addEventListener("click", event => event.target === modal ? close() : null);
    document.addEventListener("keydown", event => {
        if (event.key === "Escape" && modal.hasAttribute("open")) {
            close();
        }
    });

    return {
        open,
        close
    };
});



function buildNewChatModal() {
    window.NewChatModal = NewChatModal();
}