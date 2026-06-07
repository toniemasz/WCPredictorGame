import json

from tournament.models import Team, TeamPlayer


class PlayerImportService:

    NAME_MAPPING = {
        "DR Congo": "Congo DR",
        "Türkiye": "Turkey",
        "Côte d'Ivoire": "Ivory Coast",
        "USA": "United States",
        "Bosnia & Herzegovina": "Bosnia-Herzegovina",
        "Curacao": "Curaçao",
        "Cape Verde": "Cape Verde Islands",
    }

    @classmethod
    def check_team_mapping(cls, json_path):

        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        total = len(data)
        matched = 0
        missing = []

        print("\n=== MATCHING ===\n")

        for country_name in data.keys():

            db_name = cls.NAME_MAPPING.get(
                country_name,
                country_name
            )

            team = Team.objects.filter(
                name__iexact=db_name
            ).first()


            if team:

                matched += 1

                print(
                    f"✓ {country_name:<30} -> "
                    f"{team.code} ({team.name})"
                )

            else:

                missing.append(country_name)

                print(
                    f"✗ {country_name}"
                )

        print("\n======================")
        print(f"Dopasowano: {matched}/{total}")
        print(f"Brakujące: {len(missing)}")

        if missing:

            print("\nBrakujące drużyny:")

            for name in missing:
                print(name)

        return missing

    @classmethod
    def import_players(cls, json_path):

        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        created = 0
        updated = 0
        skipped = 0

        for country_name, players in data.items():

            db_name = cls.NAME_MAPPING.get(
                country_name,
                country_name
            )

            team = Team.objects.filter(
                name__iexact=db_name
            ).first()

            if not team:
                print(
                    f"Brak drużyny: {country_name}"
                )

                skipped += len(players)
                continue

            for player in players:

                obj, was_created = TeamPlayer.objects.update_or_create(
                    api_player_id=player["id"],
                    defaults={
                        "team": team,
                        "name": player["name"],
                        "position": player.get("position"),
                        "jersey_number": player.get("jersey_number")
                    }
                )

                if was_created:
                    created += 1
                else:
                    updated += 1

        print("\n=== IMPORT PLAYERS ===")
        print(f"Nowi: {created}")
        print(f"Zaktualizowani: {updated}")
        print(f"Pominięci: {skipped}")
        print(
            f"Łącznie: {created + updated}"
        )