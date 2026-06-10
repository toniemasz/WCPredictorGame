document.addEventListener("DOMContentLoaded", function() {
    function initializeApiUpdateCheck() {
        const banner = document.getElementById("match-api-update-banner");
        if (!banner || !banner.dataset.updateUrl) {
            return;
        }

        const initialMessage = "Uwaga: aktualizacja wyników meczów, proszę czekać.";
        const baseClasses = "mb-6 rounded-xl border px-4 py-3 text-sm font-bold shadow-lg";
        const stateClasses = {
            pending: "border-amber-400/30 bg-amber-400/10 text-amber-100 shadow-amber-950/20",
            success: "border-emerald-400/30 bg-emerald-400/10 text-emerald-100 shadow-emerald-950/20",
            error: "border-red-400/30 bg-red-400/10 text-red-100 shadow-red-950/20",
        };

        function showBanner(message, state = "pending") {
            banner.textContent = message;
            banner.className = `${baseClasses} ${stateClasses[state]}`;
        }

        function hideBanner() {
            banner.textContent = initialMessage;
            banner.className = `hidden ${baseClasses} ${stateClasses.pending}`;
        }

        const delayedBanner = setTimeout(() => {
            showBanner(initialMessage);
        }, 250);

        fetch(banner.dataset.updateUrl, {
            method: "GET",
            credentials: "same-origin",
            headers: {
                "X-Requested-With": "XMLHttpRequest",
            },
        })
        .then(response => response.json().then(data => ({
            ok: response.ok,
            data,
        })))
        .then(({ ok, data }) => {
            clearTimeout(delayedBanner);

            if (!ok || data.status === "error") {
                showBanner(
                    data.message || "Nie udało się zaktualizować wyników meczów.",
                    "error"
                );
                setTimeout(hideBanner, 5000);
                return;
            }

            if (data.updated) {
                showBanner("Wyniki meczów zostały zaktualizowane. Odświeżam widok...", "success");
                setTimeout(() => window.location.reload(), 700);
                return;
            }

            if (data.reason === "already_running") {
                showBanner(initialMessage);
                setTimeout(() => window.location.reload(), 5000);
                return;
            }

            hideBanner();
        })
        .catch(() => {
            clearTimeout(delayedBanner);
            showBanner("Nie udało się sprawdzić aktualizacji wyników.", "error");
            setTimeout(hideBanner, 5000);
        });
    }

    initializeApiUpdateCheck();

    // --- Obsługa Zakładek (Etapów) ---
    const tabs = document.querySelectorAll(".stage-tab");
    const contents = document.querySelectorAll(".stage-content");

    const savedStage = localStorage.getItem("activeStage");

    function setTabState(tab, isActive) {
        tab.dataset.active = isActive ? "true" : "false";
        tab.style.background = isActive
            ? "linear-gradient(135deg, rgba(8,145,178,.35), rgba(15,23,42,.95))"
            : "rgba(15,23,42,.72)";
        tab.style.borderColor = isActive ? "#22d3ee" : "#1e293b";
        tab.style.color = isActive ? "white" : "#94a3b8";
        tab.style.boxShadow = isActive
            ? "0 0 0 1px rgba(34,211,238,.25), 0 14px 30px rgba(8,145,178,.12)"
            : "none";
    }

    tabs.forEach(tab => {
        setTabState(tab, tab.dataset.active === "true");
    });

    if (savedStage) {
        const tab = document.querySelector(
            `.stage-tab[data-target="${savedStage}"]`
        );

        if (tab) {
            setTimeout(() => tab.click(), 50);
        }
    }

    tabs.forEach(tab => {
        tab.addEventListener("click", () => {
            localStorage.setItem(
                "activeStage",
                tab.getAttribute("data-target")
            );

            contents.forEach(content => content.classList.add("hidden"));
            tabs.forEach(t => setTabState(t, false));

            const targetId = tab.getAttribute("data-target");
            const target = document.getElementById(targetId);
            if (target) {
                target.classList.remove("hidden");
            }
            setTabState(tab, true);
        });
    });

    // --- Kompleksowy Autosave ---
    document.querySelectorAll('.prediction-form').forEach(form => {
        const inputs = form.querySelectorAll('input, select');
        const cardContainer = form.closest('.wc-card');
        const statusEl = cardContainer ? cardContainer.querySelector('.save-status') : form.nextElementSibling;
        let timeout = null;

        function triggerSave(immediate = false, reloadAfterSave = false) {
            const home = form.querySelector('[name=predicted_home]').value;
            const away = form.querySelector('[name=predicted_away]').value;

            // Zapobiega wysyłaniu niekompletnych danych liczbowych
            if (home === '' || away === '') {
                return;
            }

            if (statusEl) {
                statusEl.textContent = "Zapisywanie...";
                statusEl.className = "save-status text-center text-xs font-bold mt-2 h-4 text-slate-400 block opacity-100 transition-opacity duration-300 animate-pulse";
            }

            clearTimeout(timeout);

            const executeFetch = () => {
                const formData = new FormData(form);
                const shouldReload = reloadAfterSave;
                fetch(form.action, {
                    method: 'POST',
                    body: formData,
                    headers: { 'X-Requested-With': 'XMLHttpRequest' }
                })
                .then(response => response.json())
                .then(data => {
                    if (statusEl) {
                        statusEl.classList.remove('animate-pulse');

                        if (data.status === 'success') {
                            if (shouldReload) {
                                window.location.reload();
                            }
                            statusEl.textContent = "✓ Zapisano pomyślnie";
                            return;

                        } else {
                            statusEl.textContent = "✕ " + (data.message || "Błąd zapisu");
                            statusEl.className = "save-status text-center text-xs font-bold mt-2 h-4 text-red-400 block opacity-100 transition-opacity duration-300";
                        }
                    }
                })
                .catch(error => {
                    if (statusEl) {
                        statusEl.classList.remove('animate-pulse');
                        statusEl.textContent = "✕ Błąd połączenia sieciowego";
                        statusEl.className = "save-status text-center text-xs font-bold mt-2 h-4 text-red-400 block opacity-100 transition-opacity duration-300";
                    }
                });
            };

            if (immediate) {
                executeFetch();
            } else {
                timeout = setTimeout(executeFetch, 400);
            }
        }

        inputs.forEach(field => {
            if (field.type === 'checkbox' || field.tagName.toLowerCase() === 'select') {
                field.addEventListener('change', () => {
                        triggerSave(true, field.type === 'checkbox');
                    });
            } else {
                field.addEventListener('input', () => triggerSave(false));
                field.addEventListener('blur', () => triggerSave(true));
            }
        });
    });
});
