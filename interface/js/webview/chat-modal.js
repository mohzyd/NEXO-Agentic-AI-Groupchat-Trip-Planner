const NewChatModal = (() => {

    const modal = document.getElementById("newChatModal");
    const form = document.getElementById("newChatForm");

    const privacy = document.getElementById("chatPrivacy");
    const passwordGroup = document.getElementById("passwordGroup");
    const password = document.getElementById("chatPassword");

    const durationOptions = document.querySelectorAll(
        "#durationOptions .duration-option"
    );

    const message      = document.getElementById("chatMessage");
    const messageTitle = message.querySelector(".message-title");
    const messageText  = message.querySelector(".message-text");
    const messageIcon  = message.querySelector(".message-icon");
    const createButton = form.querySelector(".create-button");

    let selectedDuration = null;
    let isLoading = false;

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


    /* ==============================
       OPEN / CLOSE
    ============================== */

    function open() {
        modal.hidden = false;
        document.body.style.overflow = "hidden";

        setTimeout(() => {
            document.getElementById("chatName").focus();
        }, 100);
    }

    function close() {
        if (isLoading) return;

        modal.hidden = true;
        document.body.style.overflow = "";
    }


    /* ==============================
       PRIVACY
    ============================== */

    privacy.addEventListener("change", () => {

        const requiresPassword = privacy.value === "private";

        passwordGroup.hidden = !requiresPassword;
        password.required = requiresPassword;

        if (!requiresPassword) {
            password.value = "";
        }

    });


    /* ==============================
       DURATION
    ============================== */

    durationOptions.forEach(option => {

        option.addEventListener("click", () => {

            const duration = Number(option.dataset.duration);

            // Clicking the selected option deselects it.
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


    /* ==============================
       MESSAGES
    ============================== */

    function showMessage(type, text, title = null) {

        const validTypes = ["warning", "error", "success", "info"];

        if (!validTypes.includes(type)) {
            type = "info";
        }

        const defaultTitles = {
            warning: "Warning",
            error: "Something went wrong",
            success: "Success",
            info: "Information"
        };

        message.className = `warning-container ${type}`;

        messageTitle.textContent = title || defaultTitles[type];
        messageText.textContent = text;

        messageIcon.innerHTML = icons[type];

        message.hidden = false;
    }

    function hideMessage() {
        message.hidden = true;
    }


    /* ==============================
       LOADING
    ============================== */

    function setLoading(state) {

        isLoading = state;

        createButton.classList.toggle("loading", state);
        createButton.disabled = state;

        createButton.querySelector(".button-text").textContent =
            state ? "Creating..." : "Create chat";

        modal.querySelector(".close-modal").disabled = state;
    }


    /* ==============================
       FORM SUBMISSION
    ============================== */

    form.addEventListener("submit", event => {

        event.preventDefault();

        if (isLoading) return;

        hideMessage();

        const data = {
            chat_name: document.getElementById("chatName").value.trim(),

            privacy: privacy.value,

            password: privacy.value === "private"
                ? password.value
                : null,

            // null = unlimited lifetime
            lifetime: selectedDuration
        };

        if (!data.chat_name) {
            showMessage("warning", "Please enter a chat name.");
            return;
        }

        if (data.privacy === "private" && data.password.length < 6) {
            showMessage(
                "warning",
                "Your password must contain at least 6 characters."
            );
            return;
        }

        setLoading(true);

        // Send data to your application.
        form.dispatchEvent(new CustomEvent("chat:create", {
            bubbles: true,
            detail: data
        }));

    });


    /* ==============================
       EVENT LISTENERS
    ============================== */

    modal.querySelector(".close-modal").addEventListener("click", close);

    modal.addEventListener("click", event => {
        if (event.target === modal) close();
    });

    document.addEventListener("keydown", event => {
        if (event.key === "Escape" && !modal.hidden) {
            close();
        }
    });


    /* ==============================
       PUBLIC API
    ============================== */

    return {
        open,
        close,
        showMessage,
        hideMessage,
        setLoading
    };

})();


// Make it accessible from your application.
window.NewChatModal = NewChatModal;