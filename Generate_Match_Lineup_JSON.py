# Example:
# Single match mode:
# python Generate_Match_Lineup_JSON.py "D:\Data\git\VIPs of Atlanta Soccer\testing\2026-05-02-Atlanta United vs CF Montréal"
# Batch mode:
# python Generate_Match_Lineup_JSON.py "D:\Data\git\VIPs of Atlanta Soccer\testing"
# python Generate_Match_Lineup_JSON.py "testing\2026-04-18-Atlanta United vs Nashville SC" -output "images\2026-05-03-Miranchuk\GameDay_Lineup.json"
# It reads the following files from the directory: Manifest.json, StatsApi_Match.json, Key_Events.json
# It writes: GameDay_Lineup.json and GameDay_Key_Events.json

#!/usr/bin/env python3

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from rich import print

#---------------------------------------------------------------------------------------------------------------#
# Load a JSON file and return the parsed data
#---------------------------------------------------------------------------------------------------------------#
def Load_JSON_File( File_Path: Path ) -> Dict[str, Any]:

    with File_Path.open( "r", encoding="utf-8" ) as File_Handle:
        return json.load( File_Handle )

#---------------------------------------------------------------------------------------------------------------#
# Build an optional player-position lookup from roster JSON files
# Used only when match player position data is missing
#---------------------------------------------------------------------------------------------------------------#
def Build_Roster_Position_Lookup( Match_Directory: Path ) -> Dict[str, str]:

    Roster_Position_Lookup: Dict[str, str] = {}

    Roster_Files = sorted( Match_Directory.glob( "Roster - *.json" ) )

    for Roster_File in Roster_Files:

        Roster_Data = Load_JSON_File( Roster_File )
        Players = Roster_Data.get( "players", [] )

        for Player in Players:

            Player_Id = str( Player.get( "player_id", "" ) ).strip()

            if ( not Player_Id ):
                continue

            Playing_Position = (
                Player.get( "playing_position", "" )
                or Player.get( "playing_position_english", "" )
            )

            Playing_Position = str( Playing_Position or "" ).strip()

            if ( Playing_Position ):
                Roster_Position_Lookup[Player_Id] = Playing_Position

    return Roster_Position_Lookup

#---------------------------------------------------------------------------------------------------------------#
# Convert a value to a boolean
# Handles string booleans from the MLS data
#---------------------------------------------------------------------------------------------------------------#
def Value_Is_True( Value: Any ) -> bool:

    if ( isinstance( Value, bool ) ):
        return Value

    if ( isinstance( Value, str ) ):
        return Value.strip().lower() == "true"

    return False


#---------------------------------------------------------------------------------------------------------------#
# Return a player's display name
#---------------------------------------------------------------------------------------------------------------#
def Get_Player_Name( Player: Dict[str, Any] ) -> str:

    First_Name = str( Player.get( "first_name", "" ) ).strip()
    Last_Name = str( Player.get( "last_name", "" ) ).strip()

    if ( First_Name and Last_Name ):
        return f"{First_Name} {Last_Name}"

    Short_Name = str( Player.get( "short_name", "" ) ).strip()

    if ( Short_Name ):
        return Short_Name

    return ""


#---------------------------------------------------------------------------------------------------------------#
# Return a composed player name from event fields
#---------------------------------------------------------------------------------------------------------------#
def Get_Event_Name_From_Fields(
    Event: Dict[str, Any],
    First_Name_Key: str,
    Last_Name_Key: str,
) -> str:

    First_Name = str( Event.get( First_Name_Key, "" ) ).strip()
    Last_Name = str( Event.get( Last_Name_Key, "" ) ).strip()

    if ( First_Name and Last_Name ):
        return f"{First_Name} {Last_Name}"

    if ( First_Name ):
        return First_Name

    if ( Last_Name ):
        return Last_Name

    return ""


#---------------------------------------------------------------------------------------------------------------#
# Return a player's display name from a substitution event
#---------------------------------------------------------------------------------------------------------------#
def Get_Event_Player_Name( Event: Dict[str, Any], Prefix: str ) -> str:

    return Get_Event_Name_From_Fields(
        Event,
        f"{Prefix}_first_name",
        f"{Prefix}_last_name",
    )


#---------------------------------------------------------------------------------------------------------------#
# Convert detailed MLS playing positions into broad lineup groups
#---------------------------------------------------------------------------------------------------------------#
def Get_Role_Group( Playing_Position: str ) -> str:

    Position = str( Playing_Position or "" ).strip().upper()

    #if ( Position == "GK" ):
    #    return "GK"

    Goalkeeper_Positions = [
        "GK",
        "GOALKEEPER"
    ]

    Defensive_Positions = [
        "CB",
        "LCB",
        "RCB",
        "LB",
        "RB",
        "LWB",
        "RWB",
        "DEFENSE",
    ]

    Midfield_Positions = [
        "CM",
        "DM",
        "CDM",
        "AM",
        "CAM",
        "LM",
        "RM",
        "HLM",
        "HRM",
        "RDM",
        "LDM",
        "LAM",
        "RAM",
        "MIDFIELD",
    ]

    Forward_Positions = [
        "CF",
        "ST",
        "LW",
        "RW",
        "LF",
        "RF",
        "LS",
        "RS",
        "OFFENSE",
        "FORWARD"
    ]

    if ( Position in Goalkeeper_Positions ):
        return "GK"
    
    if ( Position in Defensive_Positions ):
        return "DEF"

    if ( Position in Midfield_Positions ):
        return "MID"

    if ( Position in Forward_Positions ):
        return "FWD"

    if ( "B" in Position ):
        return "DEF"

    if ( "M" in Position ):
        return "MID"

    if ( "F" in Position or "W" in Position or "S" in Position ):
        return "FWD"

    return ""


#---------------------------------------------------------------------------------------------------------------#
# Normalize a Key_Events event type into a reusable event type
#---------------------------------------------------------------------------------------------------------------#
def Normalize_Event_Type(
    Source_Type: str,
    Source_Sub_Type: str,
    Event: Dict[str, Any],
) -> str:

    Source_Type = str( Source_Type or "" ).strip().lower()
    Source_Sub_Type = str( Source_Sub_Type or "" ).strip().lower()

    if ( Source_Type == "penalties" and Source_Sub_Type == "goals" ):
        return "penalty_goal"

    if ( Source_Type == "penalties" ):
        return "penalty_miss"

    if ( Source_Type == "shot_at_goals" and Source_Sub_Type == "goals" ):
        return "goal"
    
    if ( Source_Type == "own_goals" ):
        return "own_goal"

    if ( Source_Type == "cards" ):
        Card_Color = str( Event.get( "card_color", "" ) ).strip().lower()
        Card_Color = Card_Color.replace( "_", "" ).replace( "-", "" )

        if ( Card_Color == "yellowred" ):
            return "yellowred"

        if ( Card_Color == "yellow" ):
            return "yellow"

        if ( Card_Color == "red" ):
            return "red"

        return "card"

    if ( Source_Type == "substitutions" ):
        return "substitution"

    if ( Source_Type == "fouls" ):
        return "foul"

    if ( Source_Type == "offsides" ):
        return "offside"

    if ( Source_Type == "corner_kicks" ):
        return "corner_kick"

    if ( Source_Type == "shot_at_goals" ):
        return "shot"

    return Source_Type


#---------------------------------------------------------------------------------------------------------------#
# Build one normalized key event record
# Returns a normalized event record
#---------------------------------------------------------------------------------------------------------------#
def Build_Normalized_Event( Event_Wrapper: Dict[str, Any] ) -> Dict[str, Any]:

    Source_Type = str( Event_Wrapper.get( "type", "" ) ).strip().lower()
    Source_Sub_Type = str( Event_Wrapper.get( "sub_type", "" ) ).strip().lower()
    Event = Event_Wrapper.get( "event", {} )

    Normalized_Type = Normalize_Event_Type(
        Source_Type,
        Source_Sub_Type,
        Event,
    )

    Normalized_Event: Dict[str, Any] = {
        "event_id": Event.get( "event_id", "" ),
        "type": Normalized_Type,
        "source_type": Source_Type,
        "source_sub_type": Source_Sub_Type,
        "minute": Event.get( "minute_of_play", "" ),
        "period": Event.get( "game_section", "" ),
        "event_time": Event.get( "event_time", "" ),
        "team_id": Event.get( "team_id", "" ),
        "team_name": Event.get( "team_name", "" ),
        "team_role": Event.get( "team_role", "" ),
        "team_short_name": Event.get( "team_short_name", "" ),
        "team_three_letter_code": Event.get( "team_three_letter_code", "" ),
        "player_id": Event.get( "player_id", "" ),
        "player_name": Get_Event_Name_From_Fields(
            Event,
            "player_first_name",
            "player_last_name",
        ),
        "score": Event.get( "result", "" ),
        "raw_event": Event,
    }

    if ( Source_Type == "penalties" ):

        Shot_At_Goal = Event.get( "shot_at_goal", {} )

        Normalized_Event["player_id"] = Shot_At_Goal.get(
            "player_id",
            Event.get( "prospective_taker_id", "" ),
        )

        Normalized_Event["player_name"] = Get_Event_Name_From_Fields(
            Shot_At_Goal,
            "player_first_name",
            "player_last_name",
        )

        if ( not Normalized_Event["player_name"] ):
            Normalized_Event["player_name"] = Get_Event_Name_From_Fields(
                Event,
                "prospective_taker_first_name",
                "prospective_taker_last_name",
            )

        Normalized_Event["score"] = Shot_At_Goal.get( "result", "" )
        Normalized_Event["shot_result"] = Shot_At_Goal.get( "shot_result", "" )
        Normalized_Event["penalty_result"] = Source_Sub_Type

    if ( Normalized_Type == "goal" ):
        Normalized_Event["assist_player_id"] = Event.get( "assist_player_id", "" )
        Normalized_Event["assist_player_name"] = Get_Event_Name_From_Fields(
            Event,
            "assist_player_first_name",
            "assist_player_last_name",
        )

        Normalized_Event["second_assist_player_id"] = Event.get( "second_assist_player_id", "" )
        Normalized_Event["second_assist_player_name"] = Get_Event_Name_From_Fields(
            Event,
            "second_assist_player_first_name",
            "second_assist_player_last_name",
        )

        Normalized_Event["shot_result"] = Event.get( "shot_result", "" )
        Normalized_Event["xG"] = Event.get( "xG", "" )

    if ( Normalized_Type == "own_goal" ):
        Normalized_Event["own_goal"] = True

    if ( Normalized_Type == "substitution" ):
        Normalized_Event["player_in_id"] = Event.get( "player_in_id", "" )
        Normalized_Event["player_in"] = Get_Event_Player_Name( Event, "player_in" )
        Normalized_Event["player_out_id"] = Event.get( "player_out_id", "" )
        Normalized_Event["player_out"] = Get_Event_Player_Name( Event, "player_out" )

    if ( Source_Type == "cards" ):
        Normalized_Event["card_color"] = Event.get( "card_color", "" )
        Normalized_Event["card_rating"] = Event.get( "card_rating", "" )

    if ( Source_Type == "fouls" ):
        Normalized_Event["foul_type"] = Event.get( "foul_type", "" )

        Normalized_Event["fouler_id"] = Event.get( "fouler_id", "" )
        Normalized_Event["fouler_name"] = Get_Event_Name_From_Fields(
            Event,
            "fouler_first_name",
            "fouler_last_name",
        )
        Normalized_Event["team_fouler_id"] = Event.get( "team_fouler_id", "" )
        Normalized_Event["team_fouler_name"] = Event.get( "team_fouler_name", "" )

        Normalized_Event["fouled_id"] = Event.get( "fouled_id", "" )
        Normalized_Event["fouled_name"] = Get_Event_Name_From_Fields(
            Event,
            "fouled_first_name",
            "fouled_last_name",
        )
        Normalized_Event["team_fouled_id"] = Event.get( "team_fouled_id", "" )
        Normalized_Event["team_fouled_name"] = Event.get( "team_fouled_name", "" )

    if ( Source_Type == "shot_at_goals" ):
        Normalized_Event["shot_result"] = Event.get( "shot_result", "" )
        Normalized_Event["chance_evaluation"] = Event.get( "chance_evaluation", "" )
        Normalized_Event["xG"] = Event.get( "xG", "" )
        Normalized_Event["assist_player_id"] = Event.get( "assist_player_id", "" )
        Normalized_Event["assist_player_name"] = Get_Event_Name_From_Fields(
            Event,
            "assist_player_first_name",
            "assist_player_last_name",
        )
        Normalized_Event["second_assist_player_id"] = Event.get( "second_assist_player_id", "" )
        Normalized_Event["second_assist_player_name"] = Get_Event_Name_From_Fields(
            Event,
            "second_assist_player_first_name",
            "second_assist_player_last_name",
        )

    return Normalized_Event


#---------------------------------------------------------------------------------------------------------------#
# Extract normalized key events from Key_Events.json
# Returns a reusable key events timeline
#---------------------------------------------------------------------------------------------------------------#
def Extract_Normalized_Events( Key_Events_Data: Dict[str, Any] ) -> List[Dict[str, Any]]:

    Normalized_Events: List[Dict[str, Any]] = []

    Events = Key_Events_Data.get( "events", [] )

    for Event_Wrapper in Events:
        Normalized_Events.append(
            Build_Normalized_Event( Event_Wrapper )
        )

    Normalized_Events.sort(
        key=lambda Event: (
            str( Event.get( "period", "" ) ),
            Get_Minute_Sort_Value( Event.get( "minute", "" ) ),
            str( Event.get( "event_time", "" ) ),
        )
    )


    return Normalized_Events


#---------------------------------------------------------------------------------------------------------------#
# Add an event to the Player_Events_By_Team lookup
# Returns nothing
#---------------------------------------------------------------------------------------------------------------#
def Add_Player_Event(
    Player_Events_By_Team: Dict[str, Dict[str, List[Dict[str, Any]]]],
    Team_Id: str,
    Player_Id: str,
    Event_Record: Dict[str, Any],
) -> None:

    if ( not Team_Id or not Player_Id ):
        return

    if ( Team_Id not in Player_Events_By_Team ):
        Player_Events_By_Team[Team_Id] = {}

    if ( Player_Id not in Player_Events_By_Team[Team_Id] ):
        Player_Events_By_Team[Team_Id][Player_Id] = []

    Player_Events_By_Team[Team_Id][Player_Id].append( Event_Record )


#---------------------------------------------------------------------------------------------------------------#
# Add compact player event data to the Player_Events_By_Team lookup
# Returns nothing
#---------------------------------------------------------------------------------------------------------------#
def Add_Compact_Player_Event(
    Player_Events_By_Team: Dict[str, Dict[str, List[Dict[str, Any]]]],
    Team_Id: str,
    Player_Id: str,
    Event: Dict[str, Any],
    Player_Event_Type: str,
    Player_Event_Role: str,
) -> None:

    if ( not Team_Id or not Player_Id ):
        return

    Add_Player_Event(
        Player_Events_By_Team,
        Team_Id,
        Player_Id,
        {
            "event_id": Event.get( "event_id", "" ),
            "type": Player_Event_Type,
            "minute": Event.get( "minute", "" ),
            "period": Event.get( "period", "" ),
            "role": Player_Event_Role,
            "source_type": Event.get( "source_type", "" ),
            "source_sub_type": Event.get( "source_sub_type", "" ),
        },
    )


#---------------------------------------------------------------------------------------------------------------#
# Extract compact player-linked events from normalized events
# Returns events grouped by team id and player id
#---------------------------------------------------------------------------------------------------------------#
def Extract_Player_Events_From_Normalized_Events(
    Normalized_Events: List[Dict[str, Any]],
) -> Dict[str, Dict[str, List[Dict[str, Any]]]]:

    Player_Events_By_Team: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}

    for Event in Normalized_Events:
        Event_Type = Event.get( "type", "" )
        Source_Type = Event.get( "source_type", "" )
        Team_Id = Event.get( "team_id", "" )

        if ( Event_Type == "goal" ):
            Add_Compact_Player_Event(
                Player_Events_By_Team,
                Team_Id,
                Event.get( "player_id", "" ),
                Event,
                "goal",
                "scorer",
            )

            Add_Compact_Player_Event(
                Player_Events_By_Team,
                Team_Id,
                Event.get( "assist_player_id", "" ),
                Event,
                "assist",
                "assist",
            )

            Add_Compact_Player_Event(
                Player_Events_By_Team,
                Team_Id,
                Event.get( "second_assist_player_id", "" ),
                Event,
                "second_assist",
                "second_assist",
            )

        elif ( Event_Type in [ "penalty_goal", "penalty_miss" ] ):
            Add_Compact_Player_Event(
                Player_Events_By_Team,
                Team_Id,
                Event.get( "player_id", "" ),
                Event,
                Event_Type,
                "penalty_taker",
            )

        elif ( Event_Type == "own_goal" ):
            Add_Compact_Player_Event(
                Player_Events_By_Team,
                Team_Id,
                Event.get( "player_id", "" ),
                Event,
                "own_goal",
                "own_goal",
            )

        elif ( Event_Type in [ "yellow", "yellowred", "red", "card" ] ):
            Add_Compact_Player_Event(
                Player_Events_By_Team,
                Team_Id,
                Event.get( "player_id", "" ),
                Event,
                Event_Type,
                "card",
            )

        elif ( Event_Type == "substitution" ):
            Add_Compact_Player_Event(
                Player_Events_By_Team,
                Team_Id,
                Event.get( "player_in_id", "" ),
                Event,
                "substitution_on",
                "substitution_on",
            )

            Add_Compact_Player_Event(
                Player_Events_By_Team,
                Team_Id,
                Event.get( "player_out_id", "" ),
                Event,
                "substitution_off",
                "substitution_off",
            )

        elif ( Source_Type == "fouls" ):
            Add_Compact_Player_Event(
                Player_Events_By_Team,
                Event.get( "team_fouler_id", "" ),
                Event.get( "fouler_id", "" ),
                Event,
                "foul_committed",
                "fouler",
            )

            Add_Compact_Player_Event(
                Player_Events_By_Team,
                Event.get( "team_fouled_id", "" ),
                Event.get( "fouled_id", "" ),
                Event,
                "foul_won",
                "fouled",
            )

    return Player_Events_By_Team

#---------------------------------------------------------------------------------------------------------------#
# Convert a match minute to a sortable value
# Handles minutes like 45+1 and 90+4
#---------------------------------------------------------------------------------------------------------------#
def Get_Minute_Sort_Value( Minute: Any ) -> int:

    Minute_Text = str( Minute or "" ).strip()

    if ( "+" in Minute_Text ):
        Parts = Minute_Text.split( "+", 1 )

        try:
            return int( Parts[0] ) * 100 + int( Parts[1] )
        except ValueError:
            return 0

    try:
        return int( Minute_Text ) * 100
    except ValueError:
        return 0
    
#---------------------------------------------------------------------------------------------------------------#
# Extract substitutions from normalized events
# Returns substitution events grouped by team id
#---------------------------------------------------------------------------------------------------------------#
def Extract_Substitutions_From_Normalized_Events(
    Normalized_Events: List[Dict[str, Any]],
) -> Dict[str, List[Dict[str, Any]]]:

    Substitutions_By_Team: Dict[str, List[Dict[str, Any]]] = {}

    for Event in Normalized_Events:
        if ( Event.get( "type", "" ) != "substitution" ):
            continue

        Team_Id = Event.get( "team_id", "" )

        if ( not Team_Id ):
            continue

        Substitution = {
            "event_id": Event.get( "event_id", "" ),
            "minute": Event.get( "minute", "" ),
            "player_on_id": Event.get( "player_in_id", "" ),
            "player_on": Event.get( "player_in", "" ),
            "player_off_id": Event.get( "player_out_id", "" ),
            "player_off": Event.get( "player_out", "" ),
        }

        if ( Team_Id not in Substitutions_By_Team ):
            Substitutions_By_Team[Team_Id] = []

        Substitutions_By_Team[Team_Id].append( Substitution )

    for Team_Id in Substitutions_By_Team:
        Substitutions_By_Team[Team_Id].sort(
            key=lambda Item: str( Item.get( "minute", "" ) )
        )

    return Substitutions_By_Team

#---------------------------------------------------------------------------------------------------------------#
# Return player position from match data, falling back to optional roster data
#---------------------------------------------------------------------------------------------------------------#
def Get_Player_Playing_Position(
    Player: Dict[str, Any],
    Roster_Position_Lookup: Dict[str, str],
) -> str:

    Playing_Position = (
        Player.get( "playing_position", "" )
        or Player.get( "playing_position_english", "" )
    )

    Playing_Position = str( Playing_Position or "" ).strip()

    if ( Playing_Position ):
        return Playing_Position

    Player_Id = str(
        Player.get( "person_id", "" )
        or Player.get( "player_id", "" )
    ).strip()

    if ( not Player_Id ):
        return ""

    return Roster_Position_Lookup.get( Player_Id, "" )

#---------------------------------------------------------------------------------------------------------------#
# Build a starter record for JSON output
#---------------------------------------------------------------------------------------------------------------#
def Build_Starter_Record(
    Player: Dict[str, Any],
    Substitutions: List[Dict[str, Any]],
    Player_Events: List[Dict[str, Any]],
    Roster_Position_Lookup: Dict[str, str],
) -> Dict[str, Any]:

    Player_Id = Player.get( "person_id", "" )
    Playing_Position = Get_Player_Playing_Position( Player, Roster_Position_Lookup )

    Starter_Record: Dict[str, Any] = {
        "number": Player.get( "shirt_number", "" ),
        "name": Get_Player_Name( Player ),
        "short_name": Player.get( "short_name", "" ),
        "player_id": Player_Id,
        "role": Playing_Position,
        "role_group": Get_Role_Group( Playing_Position ),
        "events": Player_Events,
    }

    if ( Value_Is_True( Player.get( "team_leader", False ) ) ):
        Starter_Record["captain"] = True

    for Substitution in Substitutions:
        if ( Substitution.get( "player_off_id", "" ) == Player_Id ):
            Starter_Record["came_off"] = {
                "minute": Substitution.get( "minute", "" ),
                "for": Substitution.get( "player_on", "" ),
                "player_id": Substitution.get( "player_on_id", "" ),
            }

    return Starter_Record


#---------------------------------------------------------------------------------------------------------------#
# Build an unused substitute record for JSON output
#---------------------------------------------------------------------------------------------------------------#
def Build_Unused_Record(
    Player: Dict[str, Any],
    Player_Events: List[Dict[str, Any]],
    Roster_Position_Lookup: Dict[str, str],
) -> Dict[str, Any]:
    
    Playing_Position = Get_Player_Playing_Position( Player, Roster_Position_Lookup )

    return {
        "number": Player.get( "shirt_number", "" ),
        "name": Get_Player_Name( Player ),
        "short_name": Player.get( "short_name", "" ),
        "player_id": Player.get( "person_id", "" ),
        "role": Playing_Position,
        "role_group": Get_Role_Group( Playing_Position ),
        "events": Player_Events,
    }

#---------------------------------------------------------------------------------------------------------------#
# Build one team section for JSON output
#---------------------------------------------------------------------------------------------------------------#
def Build_Team_Output(
    Team_Data: Dict[str, Any],
    Team_Metadata: Dict[str, Any],
    Substitutions_By_Team: Dict[str, List[Dict[str, Any]]],
    Player_Events_By_Team: Dict[str, Dict[str, List[Dict[str, Any]]]],
    Roster_Position_Lookup: Dict[str, str],
) -> Dict[str, Any]:

    Team_Id = Team_Metadata.get( "sportecId", "" )
    Players = Team_Data.get( "players", [] )
    Substitutions = Substitutions_By_Team.get( Team_Id, [] )
    Team_Player_Events = Player_Events_By_Team.get( Team_Id, {} )

    Used_Sub_Ids = set()

    for Substitution in Substitutions:
        Player_On_Id = Substitution.get( "player_on_id", "" )

        if ( Player_On_Id ):
            Used_Sub_Ids.add( Player_On_Id )

        Substitution["events"] = Team_Player_Events.get( Player_On_Id, [] )

    Starters: List[Dict[str, Any]] = []
    Unused: List[Dict[str, Any]] = []

    for Player in Players:
        Player_Id = Player.get( "person_id", "" )
        Player_Events = Team_Player_Events.get( Player_Id, [] )
        Is_Starter = Value_Is_True( Player.get( "starting", False ) )

        if ( Is_Starter ):
            Starters.append(
                Build_Starter_Record(
                    Player,
                    Substitutions,
                    Player_Events,
                    Roster_Position_Lookup,
                )
            )
        else:
            if ( Player_Id not in Used_Sub_Ids ):
                Unused.append(
                    Build_Unused_Record(
                        Player,
                        Player_Events,
                        Roster_Position_Lookup,
                    )
                )

    Team_Output = {
        "team_id": Team_Id,
        "label": Team_Metadata.get( "fullName", "" ),
        "short_name": Team_Metadata.get( "shortName", "" ),
        "abbreviation": Team_Metadata.get( "abbreviation", "" ),
        "formation": Team_Data.get( "initial_line_up", "" ),
        "starters": Starters,
        "subs": Substitutions,
        "unused": Unused,
        "unavailable": [],
        "questionable": [],
    }

    return Team_Output


#---------------------------------------------------------------------------------------------------------------#
# Build match metadata for output JSON files
#---------------------------------------------------------------------------------------------------------------#
def Build_Match_Metadata(
    Manifest_Data: Dict[str, Any],
    StatsApi_Match_Data: Dict[str, Any],
) -> Dict[str, Any]:

    Metadata = Manifest_Data.get( "Resolved_Metadata", {} )
    Match_Information = StatsApi_Match_Data.get( "match_information", {} )

    ## Add coaches, scores

    return {
        "match_id": Metadata.get( "Match_Id", Match_Information.get( "match_id", "" ) ),
        "slug": Metadata.get( "Match_Slug", "" ),
        "date": Metadata.get( "Match_Date", "" ),
        "competition": Match_Information.get( "competition_name" ) or Metadata.get( "Competition_Name" ) or "",
        "match_day": Match_Information.get( "match_day" ) if ( Match_Information.get( "match_day" ) is not None ) else ( Metadata.get( "Match_Day" ) if ( Metadata.get( "Match_Day" ) is not None ) else "" ),
        "home_team": Metadata.get( "Home_Team", "" ),
        "away_team": Metadata.get( "Away_Team", "" ),
        "home_team_id": Metadata.get( "Home_Team_Id", "" ),
        "away_team_id": Metadata.get( "Away_Team_Id", "" ),
        "venue": Metadata.get( "Venue_Name", "" ),
        "venue_city": Metadata.get( "Venue_City", "" ),
    }


#---------------------------------------------------------------------------------------------------------------#
# Build the full lineup JSON data structure
#---------------------------------------------------------------------------------------------------------------#
def Build_Lineup_Data(
    Manifest_Data: Dict[str, Any],
    StatsApi_Match_Data: Dict[str, Any],
    Normalized_Events: List[Dict[str, Any]],
    Roster_Position_Lookup: Dict[str, str],
) -> Dict[str, Any]:

    Metadata = Manifest_Data.get( "Resolved_Metadata", {} )

    Home_Metadata = {
        "sportecId": Metadata.get( "Home_Team_Id", "" ),
        "fullName": Metadata.get( "Home_Team", "" ),
        "shortName": Metadata.get( "Home_Team", "" ),
        "abbreviation": "",
    }

    Away_Metadata = {
        "sportecId": Metadata.get( "Away_Team_Id", "" ),
        "fullName": Metadata.get( "Away_Team", "" ),
        "shortName": Metadata.get( "Away_Team", "" ),
        "abbreviation": "",
    }

    Substitutions_By_Team = Extract_Substitutions_From_Normalized_Events( Normalized_Events )
    Player_Events_By_Team = Extract_Player_Events_From_Normalized_Events( Normalized_Events )

    Lineup_Data = {
        "title": "Starting Lineups",
        "display_mode": "dual",
        "focus_team": "home",
        "match": Build_Match_Metadata(
            Manifest_Data,
            StatsApi_Match_Data,
        ),
        "teams": {
            "home": Build_Team_Output(
                StatsApi_Match_Data.get( "home", {} ),
                Home_Metadata,
                Substitutions_By_Team,
                Player_Events_By_Team,
                Roster_Position_Lookup,
            ),
            "away": Build_Team_Output(
                StatsApi_Match_Data.get( "away", {} ),
                Away_Metadata,
                Substitutions_By_Team,
                Player_Events_By_Team,
                Roster_Position_Lookup,
            ),
        },
    }

    return Lineup_Data


#---------------------------------------------------------------------------------------------------------------#
# Build the key events JSON data structure
#---------------------------------------------------------------------------------------------------------------#
def Build_Key_Events_Data(
    Manifest_Data: Dict[str, Any],
    StatsApi_Match_Data: Dict[str, Any],
    Normalized_Events: List[Dict[str, Any]],
) -> Dict[str, Any]:

    return {
        "title": "GameDay Key Events",
        "match": Build_Match_Metadata(
            Manifest_Data,
            StatsApi_Match_Data,
        ),
        "events": Normalized_Events,
    }


#---------------------------------------------------------------------------------------------------------------#
# Write JSON data to disk
#---------------------------------------------------------------------------------------------------------------#
def Write_JSON_File( Output_File: Path, Data: Dict[str, Any] ) -> None:

    Output_File.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with Output_File.open( "w", encoding="utf-8" ) as File_Handle:
        json.dump(
            Data,
            File_Handle,
            ensure_ascii=False,
            indent=4,
        )

        File_Handle.write( "\n" )


#---------------------------------------------------------------------------------------------------------------#
# Resolve an output file path relative to the match directory if needed
#---------------------------------------------------------------------------------------------------------------#
def Resolve_Output_File(
    Match_Directory: Path,
    Output_Value: str,
) -> Path:

    Output_File = Path( Output_Value )

    if ( not Output_File.is_absolute() ):
        Output_File = Match_Directory / Output_File

    return Output_File


#---------------------------------------------------------------------------------------------------------------#
# Validate that the minimum required match data exists
# Raises FileNotFoundError if Manifest.json is missing
#---------------------------------------------------------------------------------------------------------------#
def Validate_Required_Files( Match_Directory: Path ) -> None:

    Required_File = Match_Directory / "Manifest.json"

    if ( not Required_File.exists() ):
        raise FileNotFoundError( f"Missing required file: {Required_File}" )

#---------------------------------------------------------------------------------------------------------------#
# Build the availability report JSON data structure
# This is a manual-edit file used by the GameDay display
#---------------------------------------------------------------------------------------------------------------#
def Build_Availability_Report_Data(
    Manifest_Data: Dict[str, Any],
    StatsApi_Match_Data: Dict[str, Any],
) -> Dict[str, Any]:

    Match_Metadata = Build_Match_Metadata(
        Manifest_Data,
        StatsApi_Match_Data,
    )

    Availability_Report_Data = {
        "title": "GameDay Availability Report",
        "match": Match_Metadata,
        "notes": "Manually update teams.home/away unavailable and questionable lists as needed. Leave arrays empty if there are no known players.",
        "example": {
            "unavailable": [
                {
                    "name": "Example Player",
                    "reason": "Example Reason",
                }
            ],
            "questionable": [
                {
                    "name": "Example Player",
                    "reason": "Example Reason",
                }
            ],
        },
        "teams": {
            "home": {
                "team_id": Match_Metadata.get( "home_team_id", "" ),
                "team": Match_Metadata.get( "home_team", "" ),
                "unavailable": [],
                "questionable": [],
            },
            "away": {
                "team_id": Match_Metadata.get( "away_team_id", "" ),
                "team": Match_Metadata.get( "away_team", "" ),
                "unavailable": [],
                "questionable": [],
            },
        },
    }

    return Availability_Report_Data

#---------------------------------------------------------------------------------------------------------------#
# Write JSON data only if the file does not already exist
# Used for manually maintained files that should not be overwritten
#---------------------------------------------------------------------------------------------------------------#
def Write_JSON_File_If_Missing( Output_File: Path, Data: Dict[str, Any] ) -> bool:

    if ( Output_File.exists() ):
        return False

    Write_JSON_File(
        Output_File,
        Data,
    )

    return True

#---------------------------------------------------------------------------------------------------------------#
# Generate GameDay files for one match directory
# Returns True if files were generated
#---------------------------------------------------------------------------------------------------------------#
def Process_Match_Directory(
    Match_Directory: Path,
    Output_Value: str,
    Events_Output_Value: Optional[str],
    Availability_Output_Value: Optional[str],
    Print_Output: bool,
) -> bool:

    Validate_Required_Files( Match_Directory )

    # Load Required files
    Manifest_Data = Load_JSON_File( Match_Directory / "Manifest.json" )

    StatsApi_Match_File = Match_Directory / "StatsApi_Match.json"
    Key_Events_File = Match_Directory / "Key_Events.json"

    StatsApi_Match_Data = {}
    Key_Events_Data = {}

    if ( StatsApi_Match_File.exists() ):
        StatsApi_Match_Data = Load_JSON_File( StatsApi_Match_File )

    if ( Key_Events_File.exists() ):
        Key_Events_Data = Load_JSON_File( Key_Events_File )

    Roster_Position_Lookup = Build_Roster_Position_Lookup( Match_Directory )

    Normalized_Events = Extract_Normalized_Events( Key_Events_Data )

    Lineup_Data = Build_Lineup_Data(
        Manifest_Data,
        StatsApi_Match_Data,
        Normalized_Events,
        Roster_Position_Lookup,
    )

    GameDay_Key_Events_Data = Build_Key_Events_Data(
        Manifest_Data,
        StatsApi_Match_Data,
        Normalized_Events,
    )

    Availability_Report_Data = Build_Availability_Report_Data(
        Manifest_Data,
        StatsApi_Match_Data,
    )

    Output_File = Resolve_Output_File(
        Match_Directory,
        Output_Value,
    )

    if ( Events_Output_Value ):
        Events_Output_File = Resolve_Output_File(
            Match_Directory,
            Events_Output_Value,
        )
    else:
        Events_Output_File = Output_File.parent / "GameDay_Key_Events.json"

    if ( Availability_Output_Value ):
        Availability_Output_File = Resolve_Output_File(
            Match_Directory,
            Availability_Output_Value,
        )
    else:
        Availability_Output_File = Output_File.parent / "GameDay_Availability_Report.json"

    Write_JSON_File( Output_File, Lineup_Data )
    Write_JSON_File( Events_Output_File, GameDay_Key_Events_Data )

    Availability_File_Created = Write_JSON_File_If_Missing(
        Availability_Output_File,
        Availability_Report_Data,
    )

    if ( Print_Output ):
        print(
            json.dumps(
                Lineup_Data,
                ensure_ascii=False,
                indent=4,
            )
        )

    print( f"[cyan]Wrote lineup JSON:[/] {Output_File}" )
    print( f"[cyan]Wrote key events JSON:[/] {Events_Output_File}" )

    if ( Availability_File_Created ):
        print( f"[cyan]Wrote availability report JSON:[/] {Availability_Output_File}" )
    else:
        print( f"Skipped availability report JSON because it already exists: {Availability_Output_File}" )

    return True

#---------------------------------------------------------------------------------------------------------------#
# Main script entry point
#---------------------------------------------------------------------------------------------------------------#
def Main() -> None:

    Parser = argparse.ArgumentParser(
        description="Generate GameDay lineup and key events JSON files from MLS match JSON files."
    )

    Parser.add_argument(
        "Match_Directory",
        help="Match directory, or parent directory containing multiple match subdirectories.",
    )

    Parser.add_argument(
        "-output",
        default="GameDay_Lineup.json",
        help="Output lineup JSON file name or full path. Default: GameDay_Lineup.json",
    )

    Parser.add_argument(
        "-events_output",
        default=None,
        help="Output key events JSON file name or full path. Default: GameDay_Key_Events.json next to the lineup output file",
    )

    Parser.add_argument(
        "-print",
        action="store_true",
        help="Print generated lineup JSON to screen.",
    )

    Parser.add_argument(
        "-availability_output",
        default=None,
        help="Output availability report JSON file name or full path. Default: GameDay_Availability_Report.json next to the lineup output file",
    )

    Args = Parser.parse_args()

    Input_Directory = Path( Args.Match_Directory ).resolve()

    if ( not Input_Directory.exists() ):
        raise FileNotFoundError( f"Directory does not exist: {Input_Directory}" )

    if ( not Input_Directory.is_dir() ):
        raise NotADirectoryError( f"Path is not a directory: {Input_Directory}" )

    Required_Files = [
        "Manifest.json",
    ]

    Is_Match_Directory = ( Input_Directory / "Manifest.json" ).exists()

    if ( Is_Match_Directory ):
        Process_Match_Directory(
            Input_Directory,
            Args.output,
            Args.events_output,
            Args.availability_output,
            Args.print,
        )

        return

    Match_Directories = []

    for Child_Path in sorted( Input_Directory.iterdir() ):

        if ( not Child_Path.is_dir() ):
            continue

        Is_Child_Match_Directory = all(
            ( Child_Path / File_Name ).exists()
            for File_Name in Required_Files
        )

        if ( Is_Child_Match_Directory ):
            Match_Directories.append( Child_Path )

    if ( len( Match_Directories ) == 0 ):
        raise FileNotFoundError(
            f"No match directories found under: {Input_Directory}"
        )

    print( f"[cyan]Found match directories:[/] {len( Match_Directories )}" )

    Success_Count = 0
    Error_Count = 0

    for Match_Directory in Match_Directories:

        print( "" )
        print( f"[cyan]Processing:[/] {Match_Directory}" )

        try:
            Process_Match_Directory(
                Match_Directory,
                Args.output,
                Args.events_output,
                Args.availability_output,
                False,
            )

            Success_Count += 1

        except Exception as Error:
            Error_Count += 1
            print( f"[red]ERROR processing {Match_Directory}:[/] {Error}" )

    print( "" )
    print( f"[cyan]Complete.[/] Success: {Success_Count}, Errors: {Error_Count}" )

    if ( Error_Count > 0 ):
        raise SystemExit( 1 )
        

if __name__ == "__main__":
    try:
        Main()
    except FileNotFoundError as Error:
        print( f"ERROR: {Error}" )
        raise SystemExit( 1 )
    except Exception as Error:
        print( f"ERROR: {Error}" )
        raise SystemExit( 1 )