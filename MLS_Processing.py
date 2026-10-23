#---------------------------------------------------------------------------------------------------------------#
# MLS Processing
#
# Process downloaded MLS match data, rosters, lineups, and GameDay reports.
#---------------------------------------------------------------------------------------------------------------#
import contextlib
import io
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from rich import print

from MLS_API import Sanitize_Path_Name, Save_Response

#---------------------------------------------------------------------------------------------------------------#
# Pull related ids, teams, and venue from DAPI, SportAPI, or StatsAPI data
# Returns a dictionary of resolved metadata
#---------------------------------------------------------------------------------------------------------------#
def Build_Resolved_Metadata(
    Match_Id: str,
    Match_Slug: str,
    Dapi_Data: Optional[Dict[str, Any]],
    SportApi_Data: Optional[Dict[str, Any]],
    StatsApi_Data: Optional[Dict[str, Any]],
    Season_Match_Window_Data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    Resolved: Dict[str, Any] = {
        "Match_Id": Match_Id,
        "Match_Slug": Match_Slug,
        "Season_Id": None,
        "Competition_Id": None,
        "Match_Date": None,
        "Home_Team": None,
        "Away_Team": None,
        "Home_Team_Id": None,
        "Away_Team_Id": None,
        "Venue_Id": None,
        "Venue_Name": None,
        "Venue_City": None,
    }

    if isinstance( Dapi_Data, dict ):
        Fields = Dapi_Data.get( "fields", {} )

        Resolved[ "Season_Id" ] = Fields.get( "seasonSportecId" )
        Resolved[ "Competition_Id" ] = Fields.get( "competitionSportecId" )

        if not Resolved[ "Home_Team_Id" ]:
            Resolved[ "Home_Team_Id" ] = Fields.get( "homeClubSportecId" )

        if not Resolved[ "Away_Team_Id" ]:
            Resolved[ "Away_Team_Id" ] = Fields.get( "awayClubSportecId" )

        Match_Date_Time = Fields.get( "matchDateTime" )

        if Match_Date_Time and ( "T" in Match_Date_Time ):
            Resolved[ "Match_Date" ] = Match_Date_Time.split( "T" )[ 0 ]

    if isinstance( SportApi_Data, dict ):
        Season_Data = SportApi_Data.get( "season", {} )
        Competition_Data = SportApi_Data.get( "competition", {} )
        Home_Data = SportApi_Data.get( "home", {} )
        Away_Data = SportApi_Data.get( "away", {} )
        Venue_Data = SportApi_Data.get( "venue", {} )

        if not Resolved[ "Season_Id" ]:
            Resolved[ "Season_Id" ] = Season_Data.get( "sportecId" )

        if not Resolved[ "Competition_Id" ]:
            Resolved[ "Competition_Id" ] = Competition_Data.get( "sportecId" )

        if not Resolved[ "Home_Team" ]:
            Resolved[ "Home_Team" ] = Home_Data.get( "fullName" )

        if not Resolved[ "Away_Team" ]:
            Resolved[ "Away_Team" ] = Away_Data.get( "fullName" )

        if not Resolved[ "Home_Team_Id" ]:
            Resolved[ "Home_Team_Id" ] = Home_Data.get( "sportecId" )

        if not Resolved[ "Away_Team_Id" ]:
            Resolved[ "Away_Team_Id" ] = Away_Data.get( "sportecId" )

        if not Resolved[ "Venue_Id" ]:
            Resolved[ "Venue_Id" ] = Venue_Data.get( "venueSportecId" )

        if not Resolved[ "Venue_Name" ]:
            Resolved[ "Venue_Name" ] = Venue_Data.get( "name" )

        if not Resolved[ "Venue_City" ]:
            Resolved[ "Venue_City" ] = Venue_Data.get( "city" )

        Match_Date_Time = SportApi_Data.get( "matchDate" )

        if Match_Date_Time and ( "T" in Match_Date_Time ) and not Resolved[ "Match_Date" ]:
            Resolved[ "Match_Date" ] = Match_Date_Time.split( "T" )[ 0 ]

    if isinstance( StatsApi_Data, dict ):
        Match_Information = StatsApi_Data.get( "match_information", {} )
        Home_Data = StatsApi_Data.get( "home", {} )
        Away_Data = StatsApi_Data.get( "away", {} )
        Environment_Data = StatsApi_Data.get( "environment", {} )

        if not Resolved[ "Season_Id" ]:
            Resolved[ "Season_Id" ] = Match_Information.get( "season_id" )

        if not Resolved[ "Competition_Id" ]:
            Resolved[ "Competition_Id" ] = Match_Information.get( "competition_id" )

        if not Resolved[ "Home_Team" ]:
            Resolved[ "Home_Team" ] = Home_Data.get( "team_name" )

        if not Resolved[ "Away_Team" ]:
            Resolved[ "Away_Team" ] = Away_Data.get( "team_name" )

        if not Resolved[ "Home_Team_Id" ]:
            Resolved[ "Home_Team_Id" ] = Home_Data.get( "team_id" )

        if not Resolved[ "Away_Team_Id" ]:
            Resolved[ "Away_Team_Id" ] = Away_Data.get( "team_id" )

        if not Resolved[ "Venue_Id" ]:
            Resolved[ "Venue_Id" ] = Environment_Data.get( "stadium_id" )

        if not Resolved[ "Venue_Name" ]:
            Resolved[ "Venue_Name" ] = Environment_Data.get( "stadium_name" )

        if not Resolved[ "Venue_City" ]:
            Resolved[ "Venue_City" ] = Environment_Data.get( "city" )

        Match_Date_Time = Match_Information.get( "planned_kickoff_time" )

        if Match_Date_Time and ( "T" in Match_Date_Time ) and not Resolved[ "Match_Date" ]:
            Resolved[ "Match_Date" ] = Match_Date_Time.split( "T" )[ 0 ]

    if ( isinstance( Season_Match_Window_Data, dict ) ):

            for Match_Data in Season_Match_Window_Data.get( "schedule", [] ):

                if ( Match_Data.get( "match_id" ) != Match_Id ):
                    continue

                if ( not Resolved[ "Venue_Id" ] ):
                    Resolved[ "Venue_Id" ] = Match_Data.get( "stadium_id" )

                if ( not Resolved[ "Venue_Name" ] ):
                    Resolved[ "Venue_Name" ] = Match_Data.get( "stadium_name" )

                if ( not Resolved[ "Venue_City" ] ):
                    Resolved[ "Venue_City" ] = Match_Data.get( "stadium_city" )

                Resolved[ "Competition_Name" ] = Match_Data.get( "competition_name" )
                Resolved[ "Match_Day" ] = Match_Data.get( "match_day" )

                break

    return Resolved


#---------------------------------------------------------------------------------------------------------------#
# Build a standardized output folder name using match date and club names
# Returns the folder name string
#---------------------------------------------------------------------------------------------------------------#
def Build_Match_Folder_Name( Resolved_Metadata: Dict[str, Any] ) -> str:
    Match_Date = Resolved_Metadata.get( "Match_Date" ) or "Unknown_Date"
    Home_Team = Resolved_Metadata.get( "Home_Team" ) or "Unknown_Home_Team"
    Away_Team = Resolved_Metadata.get( "Away_Team" ) or "Unknown_Away_Team"

    Folder_Name = f"{Match_Date}-{Home_Team} vs {Away_Team}"
    Folder_Name = Sanitize_Path_Name( Folder_Name )

    return Folder_Name


#---------------------------------------------------------------------------------------------------------------#
# Combine first and last name fields into a display name
# Returns the display name string
#---------------------------------------------------------------------------------------------------------------#
def Build_Person_Name( Person_Data: Dict[str, Any] ) -> str:
    First_Name = str( Person_Data.get( "first_name", "" ) or "" ).strip()
    Last_Name = str( Person_Data.get( "last_name", "" ) or "" ).strip()
    Display_Name = f"{First_Name} {Last_Name}".strip()

    if not Display_Name:
        Display_Name = str( Person_Data.get( "short_name", "" ) or "" ).strip()

    return Display_Name


#---------------------------------------------------------------------------------------------------------------#
# Normalize staff records from a team payload
# Returns a list of staff dictionaries
#---------------------------------------------------------------------------------------------------------------#
def Build_Staff_Metadata( Team_Data: Dict[str, Any] ) -> List[Dict[str, Any]]:
    Staff_List: List[Dict[str, Any]] = []
    Trainer_Staff = Team_Data.get( "trainer_staff", [] )

    if not isinstance( Trainer_Staff, list ):
        return Staff_List

    for Staff_Data in Trainer_Staff:
        if not isinstance( Staff_Data, dict ):
            continue

        Staff_List.append(
            {
                "Role": Staff_Data.get( "role" ),
                "Name": Build_Person_Name( Staff_Data ),
                "Short_Name": Staff_Data.get( "short_name" ),
                "Person_Id": Staff_Data.get( "person_id" ),
            }
        )

    return Staff_List


#---------------------------------------------------------------------------------------------------------------#
# Normalize official records from the match payload
# Returns a list of official dictionaries
#---------------------------------------------------------------------------------------------------------------#
def Build_Officials_Metadata( StatsApi_Data: Dict[str, Any] ) -> List[Dict[str, Any]]:
    Officials_List: List[Dict[str, Any]] = []
    Referees = StatsApi_Data.get( "referees", [] )

    if not isinstance( Referees, list ):
        return Officials_List

    for Referee_Data in Referees:
        if not isinstance( Referee_Data, dict ):
            continue

        Officials_List.append(
            {
                "Role": Referee_Data.get( "role" ),
                "Name": Build_Person_Name( Referee_Data ),
                "Short_Name": Referee_Data.get( "short_name" ),
                "Person_Id": Referee_Data.get( "person_id" ),
            }
        )

    return Officials_List


#---------------------------------------------------------------------------------------------------------------#
# Normalize kit data from a team payload
# Returns a kit dictionary
#---------------------------------------------------------------------------------------------------------------#
def Build_Kit_Metadata( Team_Data: Dict[str, Any] ) -> Dict[str, Any]:
    return {
        "Main_Color": Team_Data.get( "player_shirt_main_color" ),
        "Number_Color": Team_Data.get( "player_shirt_number_color" ),
        "Secondary_Color": Team_Data.get( "player_shirt_secondary_color" ),
        "Type": Team_Data.get( "player_shirt_type" ),
    }


#---------------------------------------------------------------------------------------------------------------#
# Normalize previous head-to-head match data from the match payload
# Returns a list of previous match dictionaries
#---------------------------------------------------------------------------------------------------------------#
def Build_Previous_Head_To_Head_Metadata( StatsApi_Data: Dict[str, Any] ) -> List[Dict[str, Any]]:
    Previous_Matches: List[Dict[str, Any]] = []
    Last_Matches = StatsApi_Data.get( "last_matches", [] )

    if not isinstance( Last_Matches, list ):
        return Previous_Matches

    for Match_Data in Last_Matches:
        if not isinstance( Match_Data, dict ):
            continue

        Previous_Matches.append(
            {
                "Match_Id": Match_Data.get( "match_id" ),
                "Match_Date": Match_Data.get( "match_date" ),
                "Season_Id": Match_Data.get( "season_id" ),
                "Competition_Id": Match_Data.get( "competition_id" ),
                "Home_Team": Match_Data.get( "home_team_name" ),
                "Away_Team": Match_Data.get( "away_team_name" ),
                "Home_Goals": Match_Data.get( "home_team_goals" ),
                "Away_Goals": Match_Data.get( "away_team_goals" ),
                "Result": Match_Data.get( "result" ),
            }
        )

    return Previous_Matches


#---------------------------------------------------------------------------------------------------------------#
# Build normalized match metadata from the StatsAPI match payload
# Returns a metadata dictionary
#---------------------------------------------------------------------------------------------------------------#
def Build_Match_Metadata(
    Match_Id: str,
    Match_Slug: str,
    StatsApi_Data: Dict[str, Any],
) -> Dict[str, Any]:
    Match_Information = StatsApi_Data.get( "match_information", {} )
    Environment_Data = StatsApi_Data.get( "environment", {} )
    Home_Data = StatsApi_Data.get( "home", {} )
    Away_Data = StatsApi_Data.get( "away", {} )

    Match_Metadata = {
        "Match": {
            "Match_Id": Match_Id,
            "Match_Slug": Match_Slug,
            "Competition_Id": Match_Information.get( "competition_id" ),
            "Competition_Name": Match_Information.get( "competition_name" ),
            "Competition_Type": Match_Information.get( "competition_type" ),
            "Season": Match_Information.get( "season" ),
            "Season_Id": Match_Information.get( "season_id" ),
            "Match_Day": Match_Information.get( "match_day" ),
            "Match_Type": Match_Information.get( "match_type" ),
            "Match_Status": Match_Information.get( "match_status" ),
            "Minute_Of_Play": Match_Information.get( "minute_of_play" ),
            "Planned_Kickoff_Time": Match_Information.get( "planned_kickoff_time" ),
            "Kickoff_Time": Match_Information.get( "kickoff_time" ),
            "Result": Match_Information.get( "result" ),
            "Penalty_Result": Match_Information.get( "result_penalty" ),
            "Home_Goals": Match_Information.get( "home_team_goals" ),
            "Away_Goals": Match_Information.get( "away_team_goals" ),
            "Home_Penalty_Goals": Match_Information.get( "home_team_penalty_goals" ),
            "Away_Penalty_Goals": Match_Information.get( "away_team_penalty_goals" ),
            "Group": Match_Information.get( "group" ),
            "Section_Name": Match_Information.get( "section_name" ),
            "Competition_Label": Match_Information.get( "competition_label" ),
            "Series_Type": Match_Information.get( "series_type" ),
        },
        "Venue": {
            "Id": Environment_Data.get( "stadium_id" ),
            "Name": Environment_Data.get( "stadium_name" ),
            "Address": Environment_Data.get( "stadium_address" ),
            "City": Environment_Data.get( "city" ),
            "Country": Environment_Data.get( "country" ),
            "Capacity": Environment_Data.get( "stadium_capacity" ),
            "Pitch_X": Environment_Data.get( "pitch_x" ),
            "Pitch_Y": Environment_Data.get( "pitch_y" ),
            "Sold_Out": Environment_Data.get( "sold_out" ),
            "Number_Of_Spectators": Environment_Data.get( "number_of_spectators" ),
        },
        "Environment": {
            "Temperature": Environment_Data.get( "temperature" ),
            "Air_Humidity": Environment_Data.get( "air_humidity" ),
            "Air_Pressure": Environment_Data.get( "air_pressure" ),
            "Precipitation": Environment_Data.get( "precipitation" ),
            "Roof": Environment_Data.get( "roof" ),
            "Floodlight": Environment_Data.get( "floodlight" ),
            "Pitch_Erosion": Environment_Data.get( "pitch_erosion" ),
        },
        "Officials": Build_Officials_Metadata( StatsApi_Data ),
        "Teams": {
            "Home": {
                "Team_Id": Home_Data.get( "team_id" ),
                "Name": Home_Data.get( "team_name" ),
                "Short_Name": Home_Data.get( "team_short_name" ),
                "Three_Letter_Code": Home_Data.get( "team_three_letter_code" ),
                "Role": Home_Data.get( "role" ),
                "Initial_Line_Up": Home_Data.get( "initial_line_up" ),
                "Latest_Line_Up": Home_Data.get( "latest_line_up" ),
                "Kit": Build_Kit_Metadata( Home_Data ),
                "Staff": Build_Staff_Metadata( Home_Data ),
            },
            "Away": {
                "Team_Id": Away_Data.get( "team_id" ),
                "Name": Away_Data.get( "team_name" ),
                "Short_Name": Away_Data.get( "team_short_name" ),
                "Three_Letter_Code": Away_Data.get( "team_three_letter_code" ),
                "Role": Away_Data.get( "role" ),
                "Initial_Line_Up": Away_Data.get( "initial_line_up" ),
                "Latest_Line_Up": Away_Data.get( "latest_line_up" ),
                "Kit": Build_Kit_Metadata( Away_Data ),
                "Staff": Build_Staff_Metadata( Away_Data ),
            },
        },
        "Previous_Head_To_Head": Build_Previous_Head_To_Head_Metadata( StatsApi_Data ),
    }

    return Match_Metadata


#---------------------------------------------------------------------------------------------------------------#
# Read a JSON file from disk
# Returns the parsed JSON dictionary
#---------------------------------------------------------------------------------------------------------------#
def Read_Json_File( File_Path: Path ) -> Dict[str, Any]:
    with File_Path.open( "r", encoding = "utf-8" ) as File_Handle:
        Data = json.load( File_Handle )

    if not isinstance( Data, dict ):
        raise RuntimeError( f"JSON file is not a dictionary: {File_Path}" )

    return Data

#---------------------------------------------------------------------------------------------------------------#
# Determine the club name from a roster JSON payload
# Returns the club name string, or an empty string if not found
#---------------------------------------------------------------------------------------------------------------#
def Get_Club_Name( Roster_Data: Dict[str, Any] ) -> str:
    Players = Roster_Data.get( "players", [] )

    if not isinstance( Players, list ):
        return ""

    for Player in Players:
        if not isinstance( Player, dict ):
            continue

        Club_Name = Player.get( "club_name", "" )

        if isinstance( Club_Name, str ) and Club_Name.strip():
            return Club_Name.strip()

    return ""

#---------------------------------------------------------------------------------------------------------------#
# Convert one roster JSON payload into formatted output rows
# Returns a list of tuples: ( shirt_number, output_line )
#---------------------------------------------------------------------------------------------------------------#
def Build_Roster_Lines( Roster_Data: Dict[str, Any], Prefix: str ) -> List[Tuple[int, str]]:
    Output_Lines: List[Tuple[int, str]] = []
    Players = Roster_Data.get( "players", [] )

    if not isinstance( Players, list ):
        return Output_Lines

    for Player in Players:
        if not isinstance( Player, dict ):
            continue

        Shirt_Number = Player.get( "shirt_number" )
        Last_Name = Player.get( "last_name", "" )

        if not isinstance( Shirt_Number, int ):
            continue

        if not isinstance( Last_Name, str ):
            continue

        Last_Name = Last_Name.strip()

        if not Last_Name:
            continue

        #Output_Line = f"{Prefix}{Shirt_Number:02d}\t{Last_Name}"
        Output_Line = f"{Prefix}{Shirt_Number:02d},{Last_Name}"
        Output_Lines.append( ( Shirt_Number, Output_Line ) )

    Output_Lines.sort( key = lambda Item: Item[ 0 ] )

    return Output_Lines

#---------------------------------------------------------------------------------------------------------------#
# Determine which roster belongs to the configured team and which belongs to the opponent
# Returns a tuple: ( My_Team_Roster_Data, Opponent_Roster_Data )
#---------------------------------------------------------------------------------------------------------------#
def Resolve_Rosters(
    First_Roster_Data: Dict[str, Any],
    Second_Roster_Data: Dict[str, Any],
    My_Team_Names: List[str],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:

    First_Club_Name = Get_Club_Name( First_Roster_Data )
    Second_Club_Name = Get_Club_Name( Second_Roster_Data )

    Normalized_Team_Names = { Name.strip().lower() for Name in My_Team_Names }

    First_Is_My_Team = First_Club_Name.strip().lower() in Normalized_Team_Names
    Second_Is_My_Team = Second_Club_Name.strip().lower() in Normalized_Team_Names

    if ( First_Is_My_Team ) and ( not Second_Is_My_Team ):
        return First_Roster_Data, Second_Roster_Data

    if ( Second_Is_My_Team ) and ( not First_Is_My_Team ):
        return Second_Roster_Data, First_Roster_Data

    raise RuntimeError(
        "Could not uniquely determine the configured team's roster.\n"
        f"First roster club:  {First_Club_Name}\n"
        f"Second roster club: {Second_Club_Name}"
    )

#---------------------------------------------------------------------------------------------------------------#
# Write output lines to a text file
# Returns nothing
#---------------------------------------------------------------------------------------------------------------#
def Write_Output_File( File_Path: Path, Output_Lines: List[str] ) -> None:
    with File_Path.open( "w", encoding = "utf-8" ) as File_Handle:
        for Line in Output_Lines:
            File_Handle.write( f"{Line}\n" )

#---------------------------------------------------------------------------------------------------------------#
# Generate or update a GameDay availability report using available match metadata
# Preserves manually entered availability information and other existing fields
# Returns True if the report was created or updated
#---------------------------------------------------------------------------------------------------------------#
def Generate_GameDay_Availability_Report( Match_Output_Directory: Path, Resolved_Metadata: Dict[str, Any] ) -> bool:
    Output_File = Match_Output_Directory / "GameDay_Availability_Report.json"

    Match_Metadata = {
        "match_id": Resolved_Metadata.get( "Match_Id" ),
        "slug": Resolved_Metadata.get( "Match_Slug" ),
        "date": Resolved_Metadata.get( "Match_Date" ),
        "competition": Resolved_Metadata.get( "Competition_Name" ) or "",
        "match_day": Resolved_Metadata.get( "Match_Day" ) if ( Resolved_Metadata.get( "Match_Day" ) is not None ) else "",
        "home_team": Resolved_Metadata.get( "Home_Team" ),
        "away_team": Resolved_Metadata.get( "Away_Team" ),
        "home_team_id": Resolved_Metadata.get( "Home_Team_Id" ),
        "away_team_id": Resolved_Metadata.get( "Away_Team_Id" ),
        "venue": Resolved_Metadata.get( "Venue_Name" ) or "",
        "venue_city": Resolved_Metadata.get( "Venue_City" ) or "",
    }

    if ( Output_File.exists() ):
        with Output_File.open( "r", encoding = "utf-8" ) as File_Handle:
            Existing_Data = json.load( File_Handle )

        Existing_Match_Metadata = Existing_Data.get( "match", {} )

        for Field_Name, Field_Value in Match_Metadata.items():
            if ( Field_Value is not None ) and ( Field_Value != "" ):
                Existing_Match_Metadata[ Field_Name ] = Field_Value

        Existing_Data[ "match" ] = Existing_Match_Metadata

        Save_Response( Output_File, Existing_Data )
        print( f"Availability report metadata updated: {Output_File}" )

        return True

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
                "team_id": Match_Metadata[ "home_team_id" ],
                "team": Match_Metadata[ "home_team" ],
                "unavailable": [],
                "questionable": [],
            },
            "away": {
                "team_id": Match_Metadata[ "away_team_id" ],
                "team": Match_Metadata[ "away_team" ],
                "unavailable": [],
                "questionable": [],
            },
        },
    }

    Save_Response( Output_File, Availability_Report_Data )
    print( f"Availability report generated: {Output_File}" )

    return True

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
def Build_GameDay_Match_Metadata(
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
        "match": Build_GameDay_Match_Metadata(
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
        "match": Build_GameDay_Match_Metadata(
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

    Match_Metadata = Build_GameDay_Match_Metadata(
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
# Generate Rosters.csv from downloaded roster JSON files
# Returns True when Rosters.csv is created successfully
#---------------------------------------------------------------------------------------------------------------#
def Generate_Rosters_CSV( Match_Output_Directory: Path, My_Team_Names: List[str] ) -> bool:
    Roster_Files = sorted( Match_Output_Directory.glob( "Roster - *.json" ) )

    if ( len( Roster_Files ) != 2 ):
        print( f"Roster CSV skipped: expected 2 roster files, found {len( Roster_Files )}", file = sys.stderr )
        return False

    try:
        First_Roster_Data = Read_Json_File( Roster_Files[ 0 ] )
        Second_Roster_Data = Read_Json_File( Roster_Files[ 1 ] )
        My_Team_Roster_Data, Opponent_Roster_Data = Resolve_Rosters( First_Roster_Data, Second_Roster_Data, My_Team_Names )
        My_Team_Lines = Build_Roster_Lines( My_Team_Roster_Data, "a" )
        Opponent_Lines = Build_Roster_Lines( Opponent_Roster_Data, "o" )
        Output_Lines = [ Item[ 1 ] for Item in My_Team_Lines ]
        Output_Lines.extend( [ Item[ 1 ] for Item in Opponent_Lines ] )
        Output_File = Match_Output_Directory / "Rosters.csv"
        Write_Output_File( Output_File, Output_Lines )
        print( f"Rosters_CSV:                 {Output_File}" )
        return True
    except Exception as Error:
        print( f"Roster CSV failed: {Error}", file = sys.stderr )
        return False


#---------------------------------------------------------------------------------------------------------------#
# Generate GameDay lineup and key events JSON directly from downloaded match data
# Returns True when generation completes successfully
#---------------------------------------------------------------------------------------------------------------#
def Generate_Match_Lineup_JSON( Match_Output_Directory: Path ) -> bool:
    try:
        Captured_Output = io.StringIO()

        with contextlib.redirect_stdout( Captured_Output ):
            Result = Process_Match_Directory(
                Match_Output_Directory,
                "GameDay_Lineup.json",
                None,
                None,
                False,
            )

        if ( not Result ):
            return False

        print( f"Match lineup JSON generated: {Match_Output_Directory}" )
        return True
    except Exception as Error:
        print( f"Match lineup JSON failed: {Error}", file = sys.stderr )
        return False
