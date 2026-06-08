document.addEventListener("DOMContentLoaded", function() {
    // --- Obsługa Zakładek (Etapów) ---
    const tabs = document.querySelectorAll(".stage-tab");
    const contents = document.querySelectorAll(".stage-content");

    const savedStage = localStorage.getItem("activeStage");

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
            tabs.forEach(t => {
                t.style.background = "rgba(12,25,60,.9)";
                t.style.borderColor = "#1f3b68";
                t.style.color = "#94a3b8";
                t.style.boxShadow = "none";
            });
            const targetId = tab.getAttribute("data-target");
            document.getElementById(targetId).classList.remove("hidden");
            tab.style.background = "linear-gradient(135deg,#00d4ff,#3b82f6)";
            tab.style.borderColor = "#22d3ee";
            tab.style.color = "white";
            tab.style.boxShadow =
                    "0 0 15px rgba(34,211,238,.4), 0 0 35px rgba(59,130,246,.25)";
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