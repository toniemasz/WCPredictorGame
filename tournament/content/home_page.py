HOME_PAGE_CONTENT = {
    "hero": {
        "title": "Przewiduj Wyniki World Cup 2026",
        "subtitle": (
            "Dołącz do rywalizacji ze znajomymi, zbieraj punkty za dokładne "
            "typy, trafiaj pierwszych strzelców bramek i zgarniaj bonusy."
        ),
        "primary_action": {
            "label": "Obstawiaj mecze",
            "url": "/matches/",
        },
        "secondary_action": {
            "label": "Zobacz ranking",
            "url": "/leaderboard/",
        },
    },
    "quick_steps": [
        {
            "number": "01",
            "title": "Typuj wyniki",
            "description": (
                "Wprowadzaj dokładne wyniki bramkowe przed rozpoczęciem "
                "każdego meczu."
            ),
            "accent": "text-cyan-400",
        },
        {
            "number": "02",
            "title": "Używaj bonusu x2",
            "description": (
                "W każdej rundzie możesz wybrać do {bonus_limit} meczów, "
                "w których zdobyte punkty zostaną podwojone."
            ),
            "accent": "text-amber-400",
        },
        {
            "number": "03",
            "title": "Zbieraj dodatkowe punkty",
            "description": (
                "Wskazuj drużynę strzelającą pierwszego gola oraz konkretnego "
                "zawodnika."
            ),
            "accent": "text-emerald-400",
        },
    ],
    "game_info": {
        "title": "Informacje o grze",
        "intro": (
            "WCPredictor 2026 to liga typowania wyników mistrzostw świata. "
            "Najważniejsze zasady i punktacja są zebrane poniżej, żeby dało "
            "się je łatwo utrzymać w jednym miejscu."
        ),
        "sections": [
            {
                "title": "Typowanie",
                "items": [
                    "Typ można zapisać tylko przed rozpoczęciem meczu.",
                    (
                        "Po starcie meczu typ i bonus zostają zablokowane, "
                        "a wynik trafia do rozliczenia punktów."
                    ),
                    (
                        "Dla meczów nierozpoczętych typy innych graczy są "
                        "ukryte na ich profilach."
                    ),
                ],
            },
            {
                "title": "Punktacja",
                "items": [
                    "Dokładny wynik: +{correct_result_points} pkt.",
                    (
                        "Poprawna liczba goli jednej drużyny: "
                        "+{correct_home_or_away_goals_points} pkt."
                    ),
                    "Poprawna różnica bramek: +{correct_goal_diff_points} pkt.",
                    (
                        "Poprawny kierunek meczu, czyli wygrana/remis: "
                        "+{correct_home_or_away_win_points} pkt."
                    ),
                    "Trafiona pierwsza drużyna z golem: +{correct_first_team_scored} pkt.",
                    "Trafiony pierwszy strzelec: +{correct_first_scorer_points} pkt.",
                ],
            },
            {
                "title": "Bonusy",
                "items": [
                    (
                        "Bonus x2 podwaja wynik punktowy dla wybranego meczu. "
                        "Limit: {bonus_limit} na rundę."
                    ),
                    (
                        "Bonus za underdoga nalicza dodatkowe punkty, gdy "
                        "trafisz zwycięstwo drużyny z wysokim kursem."
                    ),
                    (
                        "Wysokość bonusu underdoga rośnie logarytmicznie od "
                        "kursu powyżej 3.00."
                    ),
                ],
            },
            {
                "title": "Ranking i profile",
                "items": [
                    "Leaderboard sortuje graczy po sumie punktów z typowań.",
                    "Na profilu zobaczysz kupony gracza pogrupowane po rundach.",
                    "Avatar profilu jest wybierany z dostępnych grafik w aplikacji.",
                ],
            },
        ],
    },
    "patch_notes": {
        "title": "Patch notes",
        "items": [
            {
                "version": "2026.06.10",
                "title": "Profile, avatary i strona główna",
                "changes": [
                    "Naprawiono wyświetlanie avatarów na leaderboardzie.",
                    "Przeniesiono część logiki widoków do serwisów.",
                    "Dodano edytowalną sekcję informacji o grze na ekranie głównym.",
                ],
            },
            {
                "version": "2026.06.08",
                "title": "Punktacja i bonusy",
                "changes": [
                    "Dodano szczegółowe rozbicie punktów za typy.",
                    "Dodano limit bonusu x2 na rundę.",
                    "Dodano bonus za trafienie underdoga.",
                ],
            },
        ],
    },
}
