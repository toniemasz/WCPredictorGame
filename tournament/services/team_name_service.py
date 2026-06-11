class TeamNameService:
    SESSION_KEY = "country_language"
    LANGUAGE_PL = "pl"
    LANGUAGE_EN = "en"
    SUPPORTED_LANGUAGES = (LANGUAGE_PL, LANGUAGE_EN)

    @classmethod
    def get_language(cls, request):
        language = request.session.get(cls.SESSION_KEY, cls.LANGUAGE_PL)
        if language not in cls.SUPPORTED_LANGUAGES:
            return cls.LANGUAGE_PL
        return language

    @classmethod
    def set_language(cls, request, language):
        if language not in cls.SUPPORTED_LANGUAGES:
            raise ValueError("Nieobsługiwany język nazw krajów.")

        request.session[cls.SESSION_KEY] = language

    @classmethod
    def get_team_name(cls, team, language):
        if language == cls.LANGUAGE_EN:
            return team.name
        return team.name_pl or team.name

    @classmethod
    def annotate_match(cls, match, language):
        match.home_team.display_name = cls.get_team_name(match.home_team, language)
        match.away_team.display_name = cls.get_team_name(match.away_team, language)
        return match
