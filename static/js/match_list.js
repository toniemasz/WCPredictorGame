document.addEventListener("DOMContentLoaded", function() {
        const tabs = document.querySelectorAll(".stage-tab");
        const contents = document.querySelectorAll(".stage-content");

        tabs.forEach(tab => {
            tab.addEventListener("click", () => {
                contents.forEach(content => content.classList.add("hidden"));
                tabs.forEach(t => {
                    t.classList.remove("bg-cyan-500", "text-black", "shadow-[0_0_15px_rgba(6,182,212,0.3)]");
                    t.classList.add("bg-slate-900", "border", "border-slate-800", "text-slate-400");
                });
                const targetId = tab.getAttribute("data-target");
                document.getElementById(targetId).classList.remove("hidden");
                tab.classList.remove("bg-slate-900", "border", "border-slate-800", "text-slate-400");
                tab.classList.add("bg-cyan-500", "text-black", "shadow-[0_0_15px_rgba(6,182,212,0.3)]");
            });
        });

        const stages = document.querySelectorAll(".stage-content");
            stages.forEach(stage => {
                const checkboxes = stage.querySelectorAll('.bonus-checkbox');

                const limit = parseInt(stage.dataset.bonusLimit) || 2;

                function toggleCheckboxes() {
                    // Zliczamy tylko te, które są zaznaczone w TEJ konkretnej fazie
                    const checkedCount = stage.querySelectorAll('.bonus-checkbox:checked').length;
                    const isLimitReached = checkedCount >= limit;

                    checkboxes.forEach(cb => {
                        if (cb.dataset.serverLocked === "true") return;

                        const label = cb.closest(".bonus-label");

                        // Logika: Jeśli osiągnięto limit I ten konkretny nie jest zaznaczony -> blokuj
                        if (isLimitReached && !cb.checked) {
                            cb.disabled = true;
                            label.classList.add("opacity-20", "cursor-not-allowed", "grayscale");
                            label.classList.remove("cursor-pointer", "hover:text-amber-300");
                            cb.classList.add("hidden");
                        } else {
                            // Odblokuj w przeciwnym razie
                            cb.disabled = false;
                            label.classList.remove("opacity-20", "cursor-not-allowed", "grayscale");
                            label.classList.add("cursor-pointer", "hover:text-amber-300");
                            cb.classList.remove("hidden");
                        }
                    });
                }

                checkboxes.forEach(cb => cb.addEventListener("change", toggleCheckboxes));
                toggleCheckboxes(); // Inicjalizacja przy ładowaniu
            });

        document.querySelectorAll('.prediction-form').forEach(form => {
            const inputs = form.querySelectorAll('input, select');
            const statusEl = form.nextElementSibling;
            let timeout = null;

            inputs.forEach(field => {
                const eventType = field.type === 'checkbox' ? 'change' : 'input';
                field.addEventListener(eventType, () => {
                    const home = form.querySelector('[name=predicted_home]').value;
                    const away = form.querySelector('[name=predicted_away]').value;
                    if (home === '' || away === '') return;

                    statusEl.textContent = "Zapisywanie...";
                    statusEl.className = "save-status text-right text-xs font-bold mt-2 h-4 text-slate-400 block opacity-100 transition-opacity duration-300";
                    clearTimeout(timeout);

                    const delay = field.type === 'checkbox' ? 0 : 600;
                    timeout = setTimeout(() => {
                        const formData = new FormData(form);
                        fetch(form.action, {
                            method: 'POST',
                            body: formData,
                            headers: { 'X-Requested-With': 'XMLHttpRequest' }
                        })
                        .then(response => response.json())
                        .then(data => {
                            if (data.status === 'success') {
                                statusEl.textContent = "✓ Zapisano pomyślnie";
                                statusEl.className = "save-status text-right text-xs font-bold mt-2 h-4 text-green-400 block opacity-100 transition-opacity duration-300";
                                setTimeout(() => {
                                    statusEl.classList.remove('opacity-100');
                                    statusEl.classList.add('opacity-0');
                                }, 2500);
                            } else {
                                statusEl.textContent = "✕ " + data.message;
                                statusEl.className = "save-status text-right text-xs font-bold mt-2 h-4 text-red-400 block opacity-100 transition-opacity duration-300";
                            }
                        })
                        .catch(error => {
                            statusEl.textContent = "✕ Błąd połączenia";
                            statusEl.className = "save-status text-right text-xs font-bold mt-2 h-4 text-red-400 block opacity-100 transition-opacity duration-300";
                        });
                    }, delay);
                });
            });
        });
    });