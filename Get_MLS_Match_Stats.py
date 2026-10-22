#---------------------------------------------------------------------------------------------------------------#
# py -m pip install --upgrade package_name
#---------------------------------------------------------------------------------------------------------------#

#---------------------------------------------------------------------------------------------------------------#
# Download MLS match JSON data for a single match
#
# What it does:
#   - Accepts an MLS match URL, slug, or match id
#   - Resolves the match slug to obtain the Sportec match id and related ids
#   - Builds known MLS JSON endpoints for that match
#   - Downloads each JSON payload into a match-specific output directory
#   - Pulls all commentary pages until next_page_token is no longer returned
#   - De-duplicates commentary rows by event_id
#   - Saves the merged commentary into a single Commentary.json file
#   - Saves a manifest file containing the resolved ids and endpoint list
#
# Notes:
#   - English is hardcoded for all supported endpoints
#   - This script downloads individual JSON files, not one combined file
#   - A separate script can parse and normalize the returned JSON later
#---------------------------------------------------------------------------------------------------------------#

import argparse
import json
import re
import sys
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from rich import print
from rich.table import Table
import requests


# Example Usage
# python Get_MLS_Match_Stats.py "https://www.mlssoccer.com/competitions/mls-regular-season/2026/matches/atlvsclb-04-04-2026/stats" -output "testing"


#---------------------------------------------------------------------------------------------------------------#
# Create a requests session with common headers
# Returns the Session object
#---------------------------------------------------------------------------------------------------------------#
def Create_Session() -> requests.Session:
    Session = requests.Session()

    Session.headers.update(
        {
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json, text/plain, */*",
        }
    )

    return Session


#---------------------------------------------------------------------------------------------------------------#
# Extract the match slug from a full MLS match URL
# Returns the slug string, or None if not found
#---------------------------------------------------------------------------------------------------------------#
def Extract_Slug_From_Url( Value: str ) -> Optional[str]:
    Parsed = urlparse( Value )
    Path_Parts = [ Part for Part in Parsed.path.split( "/" ) if Part ]

    for Index, Part in enumerate( Path_Parts ):
        if ( Part == "matches" ) and ( Index + 1 < len( Path_Parts ) ):
            return Path_Parts[ Index + 1 ]

    return None

#---------------------------------------------------------------------------------------------------------------#
# Run an external Python script and capture the result
# Returns the CompletedProcess object
#---------------------------------------------------------------------------------------------------------------#
def Run_Python_Script( Command: List[str] ) -> subprocess.CompletedProcess:
    Result = subprocess.run(
        Command,
        capture_output = True,
        text = True,
        encoding = "utf-8",
        errors = "replace",
    )

    return Result


#---------------------------------------------------------------------------------------------------------------#
# Generate Rosters.csv from downloaded roster JSON files
# Returns True when Rosters.csv is created successfully
#---------------------------------------------------------------------------------------------------------------#
def Generate_Rosters_CSV( Match_Output_Directory: Path ) -> bool:
    Roster_Files = sorted( Match_Output_Directory.glob( "Roster - *.json" ) )

    if ( len( Roster_Files ) != 2 ):
        print(
            f"Roster CSV skipped: expected 2 roster files, found {len( Roster_Files )}",
            file = sys.stderr,
        )

        return False

    Output_File = Match_Output_Directory / "Rosters.csv"

    Command = [
        sys.executable,
        "Get_MLS_Rosters.py",
        str( Roster_Files[ 0 ] ),
        str( Roster_Files[ 1 ] ),
        "-output",
        str( Output_File ),
    ]

    Result = Run_Python_Script( Command )

    if ( Result.returncode == 0 ):
        print( f"Rosters_CSV:                 {Output_File}" )
        return True

    Error_Text = Result.stderr.strip()

    if not Error_Text:
        Error_Text = Result.stdout.strip()

    Error_First_Line = "Get_MLS_Rosters.py failed."

    for Error_Line in Error_Text.splitlines():
        Error_Line = Error_Line.strip()

        if Error_Line:
            Error_First_Line = Error_Line
            break

    print( f"Roster CSV failed: {Error_First_Line}", file = sys.stderr )

    return False

#---------------------------------------------------------------------------------------------------------------#
# Determine whether the supplied value is a Sportec match id
# Returns True if it looks like MLS-MAT-xxxxxx
#---------------------------------------------------------------------------------------------------------------#
def Is_Match_Id( Value: str ) -> bool:
    return re.fullmatch( r"MLS-MAT-[A-Z0-9]+", Value.strip() ) is not None


#---------------------------------------------------------------------------------------------------------------#
# Determine whether the supplied value looks like an MLS match slug
# Returns True if it resembles atlvsdc-03-21-2026
#---------------------------------------------------------------------------------------------------------------#
def Is_Match_Slug( Value: str ) -> bool:
    return re.fullmatch( r"[a-z0-9-]+", Value.strip() ) is not None


#---------------------------------------------------------------------------------------------------------------#
# Clean text so it can be safely used in a Windows directory or file name
# Returns the cleaned string
#---------------------------------------------------------------------------------------------------------------#
def Sanitize_Path_Name( Value: str ) -> str:
    Cleaned_Value = Value.strip()

    Cleaned_Value = Cleaned_Value.replace( ":", "" )
    Cleaned_Value = Cleaned_Value.replace( "/", "-" )
    Cleaned_Value = Cleaned_Value.replace( "\\", "-" )
    Cleaned_Value = Cleaned_Value.replace( "*", "" )
    Cleaned_Value = Cleaned_Value.replace( "?", "" )
    Cleaned_Value = Cleaned_Value.replace( "\"", "'" )
    Cleaned_Value = Cleaned_Value.replace( "<", "" )
    Cleaned_Value = Cleaned_Value.replace( ">", "" )
    Cleaned_Value = Cleaned_Value.replace( "|", "" )

    Cleaned_Value = re.sub( r"\s+", " ", Cleaned_Value )

    return Cleaned_Value


#---------------------------------------------------------------------------------------------------------------#
# Download JSON from an endpoint
# Returns a tuple: ( success, parsed_json_or_text, status_code, content_type )
#---------------------------------------------------------------------------------------------------------------#
def Get_Json( Session: requests.Session, Url: str, Timeout: int = 30 ) -> Tuple[bool, Any, int, str]:
    try:
        Response = Session.get( Url, timeout = Timeout )
    except requests.RequestException as Error:
        return False, { "error": str( Error ), "url": Url }, 0, ""

    Content_Type = Response.headers.get( "Content-Type", "" )

    if ( Response.status_code != 200 ):
        try:
            Error_Data = Response.json()
        except ValueError:
            Error_Data = Response.text

        return False, Error_Data, Response.status_code, Content_Type

    try:
        return True, Response.json(), Response.status_code, Content_Type
    except ValueError:
        return False, Response.text, Response.status_code, Content_Type


#---------------------------------------------------------------------------------------------------------------#
# Save JSON or text data to disk
# Returns nothing
#---------------------------------------------------------------------------------------------------------------#
def Save_Response( File_Path: Path, Data: Any ) -> None:
    File_Path.parent.mkdir( parents = True, exist_ok = True )

    with File_Path.open( "w", encoding = "utf-8" ) as File_Handle:
        if isinstance( Data, ( dict, list ) ):
            json.dump( Data, File_Handle, indent = 4, ensure_ascii = False )
        else:
            File_Handle.write( str( Data ) )

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
# Resolve a slug using the DAPI content endpoint
# Returns the parsed DAPI JSON dictionary
#---------------------------------------------------------------------------------------------------------------#
def Resolve_Match_From_Slug( Session: requests.Session, Match_Slug: str ) -> Dict[str, Any]:
    Url = f"https://dapi.mlssoccer.com/v2/content/en-us/matches/{Match_Slug}"

    Success, Data, Status_Code, _ = Get_Json( Session, Url )

    if not Success:
        raise RuntimeError( f"Failed to resolve slug [{Match_Slug}] via DAPI. Status={Status_Code}" )

    if not isinstance( Data, dict ):
        raise RuntimeError( f"DAPI response for slug [{Match_Slug}] was not a JSON object." )

    return Data


#---------------------------------------------------------------------------------------------------------------#
# Resolve a match id using the SportAPI match endpoint
# Returns the parsed SportAPI JSON dictionary
#---------------------------------------------------------------------------------------------------------------#
def Resolve_Match_From_Id( Session: requests.Session, Match_Id: str ) -> Dict[str, Any]:
    Url = f"https://sportapi.mlssoccer.com/api/matches/{Match_Id}"

    Success, Data, Status_Code, _ = Get_Json( Session, Url )

    if not Success:
        raise RuntimeError( f"Failed to resolve match id [{Match_Id}] via SportAPI. Status={Status_Code}" )

    if not isinstance( Data, dict ):
        raise RuntimeError( f"SportAPI response for match id [{Match_Id}] was not a JSON object." )

    return Data

#---------------------------------------------------------------------------------------------------------------#
# Resolve a match id using the StatsAPI match endpoint
# Returns the parsed StatsAPI JSON dictionary
#---------------------------------------------------------------------------------------------------------------#
def Resolve_Match_From_StatsApi( Session: requests.Session, Match_Id: str ) -> Dict[str, Any]:
    Url = f"https://stats-api.mlssoccer.com/matches/{Match_Id}"

    Success, Data, Status_Code, _ = Get_Json( Session, Url )

    if not Success:
        raise RuntimeError( f"Failed to resolve match id [{Match_Id}] via StatsAPI. Status={Status_Code}" )

    if not isinstance( Data, dict ):
        raise RuntimeError( f"StatsAPI response for match id [{Match_Id}] was not a JSON object." )

    return Data

#---------------------------------------------------------------------------------------------------------------#
# Build the list of known endpoints to download for a match
# Returns a dictionary of endpoint_name -> url
#---------------------------------------------------------------------------------------------------------------#
def Build_Endpoint_List(
    Match_Id: str,
    Match_Slug: str,
    Season_Id: Optional[str],
    Competition_Id: Optional[str],
    Home_Team_Id: Optional[str],
    Away_Team_Id: Optional[str],
    Home_Team: Optional[str],
    Away_Team: Optional[str],
    Match_Date: Optional[str],
) -> Dict[str, str]:
    Endpoints: Dict[str, str] = {}

    Endpoints[ "Vocabs" ] = "https://www.mlssoccer.com/vocabs/en"
    Endpoints[ "Dapi_Match" ] = f"https://dapi.mlssoccer.com/v2/content/en-us/matches/{Match_Slug}"
    #Endpoints[ "StatsApi_Match" ] = f"https://stats-api.mlssoccer.com/matches/{Match_Id}"
    #Endpoints[ "SportApi_Match" ] = f"https://sportapi.mlssoccer.com/api/matches/{Match_Id}"
    Endpoints[ "Key_Events" ] = f"https://stats-api.mlssoccer.com/matches/{Match_Id}/key_events?per_page=1000"
    Endpoints[ "Club_Statistics" ] = f"https://stats-api.mlssoccer.com/statistics/clubs/matches/{Match_Id}"
    #Endpoints[ "Club_Possession" ] = f"https://stats-api.mlssoccer.com/statistics/clubs/matches/{Match_Id}/possession?scope=all"
    Endpoints[ "Player_Statistics" ] = f"https://stats-api.mlssoccer.com/statistics/players/matches/{Match_Id}?per_page=200"

    if ( Competition_Id != "MLS-COM-000003" ):
        Endpoints[ "Club_Possession" ] = f"https://stats-api.mlssoccer.com/statistics/clubs/matches/{Match_Id}/possession?scope=all"

    if ( Season_Id is not None ) and ( Competition_Id is not None ):
        Endpoints[ "Club_Season_Statistics" ] = (
            "https://stats-api.mlssoccer.com/statistics/clubs/competitions/"
            f"{Competition_Id}/seasons/{Season_Id}?per_page=50"
        )

    if ( Season_Id is not None ) and ( Home_Team_Id is not None ):
        Home_Team_File_Name = Sanitize_Path_Name( Home_Team or "Home Team" )
        Endpoints[ f"Roster - {Home_Team_File_Name}" ] = (
            "https://stats-api.mlssoccer.com/players/seasons/"
            f"{Season_Id}/clubs/{Home_Team_Id}?per_page=100"
        )

    if ( Season_Id is not None ) and ( Away_Team_Id is not None ):
        Away_Team_File_Name = Sanitize_Path_Name( Away_Team or "Away Team" )
        Endpoints[ f"Roster - {Away_Team_File_Name}" ] = (
            "https://stats-api.mlssoccer.com/players/seasons/"
            f"{Season_Id}/clubs/{Away_Team_Id}?per_page=100"
        )

    if ( Season_Id is not None ) and ( Competition_Id is not None ) and ( Match_Date is not None ):
        Endpoints[ "Season_Match_Window" ] = (
            "https://stats-api.mlssoccer.com/matches/seasons/"
            f"{Season_Id}"
            f"?match_date%5Bgte%5D={Match_Date}"
            f"&match_date%5Blte%5D={Match_Date}"
            f"&competition_id={Competition_Id}"
            "&per_page=100"
        )

    return Endpoints


#---------------------------------------------------------------------------------------------------------------#
# Normalize the user's input into match id and slug
# Returns a tuple: ( match_id, match_slug, dapi_data, sportapi_data )
#---------------------------------------------------------------------------------------------------------------#
def Resolve_Input(
    Session: requests.Session,
    Input_Value: str,
) -> Tuple[str, str, Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    Input_Value = Input_Value.strip()

    if ( Input_Value.startswith( "http://" ) ) or ( Input_Value.startswith( "https://" ) ):
        Match_Slug = Extract_Slug_From_Url( Input_Value )

        if ( Match_Slug is None ):
            raise RuntimeError( "Could not extract match slug from the supplied URL." )

        Dapi_Data = Resolve_Match_From_Slug( Session, Match_Slug )
        Match_Id = Dapi_Data.get( "fields", {} ).get( "sportecId" )

        if not Match_Id:
            raise RuntimeError( f"DAPI payload for slug [{Match_Slug}] did not contain fields.sportecId." )

        return Match_Id, Match_Slug, Dapi_Data, None

    if Is_Match_Id( Input_Value ):
        Match_Id = Input_Value
        SportApi_Data = Resolve_Match_From_Id( Session, Match_Id )
        Match_Slug = SportApi_Data.get( "slug" )

        if not Match_Slug:
            raise RuntimeError( f"SportAPI payload for match id [{Match_Id}] did not contain slug." )

        return Match_Id, Match_Slug, None, SportApi_Data

    if Is_Match_Slug( Input_Value ):
        Match_Slug = Input_Value
        Dapi_Data = Resolve_Match_From_Slug( Session, Match_Slug )
        Match_Id = Dapi_Data.get( "fields", {} ).get( "sportecId" )

        if not Match_Id:
            raise RuntimeError( f"DAPI payload for slug [{Match_Slug}] did not contain fields.sportecId." )

        return Match_Id, Match_Slug, Dapi_Data, None

    raise RuntimeError(
        "Input must be one of the following:\n"
        "  - Full match URL\n"
        "  - Match slug, such as atlvsdc-03-21-2026\n"
        "  - Match id, such as MLS-MAT-0009CR"
    )


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
# Download all pages of commentary for a match and merge them into one payload
# Returns a tuple: ( combined_payload, page_count, duplicate_count )
#---------------------------------------------------------------------------------------------------------------#
def Download_All_Commentary(
    Session: requests.Session,
    Match_Id: str,
) -> Tuple[bool, Dict[str, Any], int, int, int, Any]:
    Commentary_Items: List[Dict[str, Any]] = []
    Seen_Event_Ids = set()
    Match_Info: Dict[str, Any] = {}
    Page_Count = 0
    Duplicate_Count = 0
    Page_Token: Optional[str] = None
    Last_Status_Code = 200
    Error_Data: Any = None

    while True:
        if Page_Token is None:
            Url = f"https://stats-api.mlssoccer.com/matches/{Match_Id}/commentary?language=en"
        else:
            Url = (
                f"https://stats-api.mlssoccer.com/matches/{Match_Id}/commentary"
                f"?page_token={Page_Token}&language=en"
            )

        Success, Data, Status_Code, _ = Get_Json( Session, Url )
        Last_Status_Code = Status_Code

        if not Success:
            Error_Data = Data
            return False, {}, Page_Count, Duplicate_Count, Last_Status_Code, Error_Data

        if not isinstance( Data, dict ):
            Error_Data = { "error": "Commentary response was not a JSON object." }
            return False, {}, Page_Count, Duplicate_Count, Last_Status_Code, Error_Data

        Page_Count += 1

        Page_Commentary = Data.get( "commentary", [] )
        if isinstance( Page_Commentary, list ):
            for Commentary_Event in Page_Commentary:
                if not isinstance( Commentary_Event, dict ):
                    continue

                Event_Id = Commentary_Event.get( "event_id" )

                if Event_Id is None:
                    Commentary_Items.append( Commentary_Event )
                    continue

                if Event_Id in Seen_Event_Ids:
                    Duplicate_Count += 1
                    continue

                Seen_Event_Ids.add( Event_Id )
                Commentary_Items.append( Commentary_Event )

        if ( not Match_Info ) and isinstance( Data.get( "match_info" ), dict ):
            Match_Info = Data.get( "match_info", {} )

        Page_Token = Data.get( "next_page_token" )

        if not Page_Token:
            break

    Combined_Payload = {
        "commentary": Commentary_Items,
        "match_info": Match_Info,
    }

    return True, Combined_Payload, Page_Count, Duplicate_Count, Last_Status_Code, None


#---------------------------------------------------------------------------------------------------------------#
# Download all endpoints and save them to disk
# Returns a summary dictionary
#---------------------------------------------------------------------------------------------------------------#
def Download_All_Endpoints(
    Session: requests.Session,
    Endpoints: Dict[str, str],
    Output_Directory: Path,
) -> Dict[str, Any]:
    Summary: Dict[str, Any] = {
        "Downloaded": {},
        "Failed": {},
    }

    Results_Table = Create_Results_Table()

    for Endpoint_Name, Url in Endpoints.items():
        Safe_File_Name = f"{Endpoint_Name}.json"
        Output_File = Output_Directory / Safe_File_Name

        Success, Data, Status_Code, Content_Type = Get_Json( Session, Url )

        Record = {
            "Url": Url,
            "Status_Code": Status_Code,
            "Content_Type": Content_Type,
            "Output_File": str( Output_File ),
        }

        if Success:
            Save_Response( Output_File, Data )
            Summary[ "Downloaded" ][ Endpoint_Name ] = Record

            Results_Table.add_row(
                Endpoint_Name,
                "[green]OK[/]",
                str( Status_Code ),
                #str( Output_File.name ),
                Url,
            )
        else:
            Error_File = Output_Directory / f"{Endpoint_Name}.error.json"
            #Save_Response( Error_File, Data )

            Record[ "Output_File" ] = str( Error_File )
            Summary[ "Failed" ][ Endpoint_Name ] = Record

            Results_Table.add_row(
                Endpoint_Name,
                "[red]Failed[/]",
                str( Status_Code ),
                #str( Error_File.name ),
                Url,
            )

    print()
    print( Results_Table )

    return Summary


#---------------------------------------------------------------------------------------------------------------#
# Create a Rich table used for endpoint download results
# Returns the Table object
#---------------------------------------------------------------------------------------------------------------#
def Create_Results_Table() -> Table:
    Results_Table = Table( show_header = True, header_style = "bold" )

    Results_Table.add_column( "Endpoint", style = "cyan", no_wrap = True )
    Results_Table.add_column( "Status", no_wrap = True )
    Results_Table.add_column( "Code", no_wrap = True )
    #Results_Table.add_column( "File", overflow = "fold" )
    Results_Table.add_column( "URL", overflow = "fold" )

    return Results_Table

#---------------------------------------------------------------------------------------------------------------#
# Generate GameDay lineup JSON files from the downloaded match data
# Returns True when Generate_Match_Lineup_JSON.py completes successfully
#---------------------------------------------------------------------------------------------------------------#
def Generate_Match_Lineup_JSON( Match_Output_Directory: Path ) -> bool:
    Script_File = Path( __file__ ).resolve().parent / "Generate_Match_Lineup_JSON.py"

    Command = [
        sys.executable,
        str( Script_File ),
        str( Match_Output_Directory ),
    ]

    Result = Run_Python_Script( Command )

    if ( Result.returncode == 0 ):

        if ( "Lineup generation skipped." in Result.stdout ):
            print( Result.stdout.strip() )
            return False

        print( f"Match lineup JSON generated: {Match_Output_Directory}" )
        return True

    Error_Text = Result.stderr.strip()

    if ( not Error_Text ):
        Error_Text = Result.stdout.strip()

    Error_First_Line = "Generate_Match_Lineup_JSON.py failed."

    for Error_Line in Error_Text.splitlines():
        Error_Line = Error_Line.strip()

        if ( Error_Line ):
            Error_First_Line = Error_Line
            break

    print( f"Match lineup JSON failed: {Error_First_Line}", file = sys.stderr )

    return False


#---------------------------------------------------------------------------------------------------------------#
# Main entry point
# Returns process exit code
#---------------------------------------------------------------------------------------------------------------#
def Main() -> int:
    Parser = argparse.ArgumentParser(
        description = "Download MLS JSON data for a single match"
    )

    Parser.add_argument(
        "Input_Value",
        help = "MLS match URL, slug, or match id"
    )

    Parser.add_argument(
        "-output",
        default = "Match_Stats",
        help = "Base output directory"
    )

    Arguments = Parser.parse_args()

    Session = Create_Session()

    try:
        Match_Id, Match_Slug, Dapi_Data, SportApi_Data = Resolve_Input(
            Session = Session,
            Input_Value = Arguments.Input_Value,
        )

        if Dapi_Data is None:
            Dapi_Data = Resolve_Match_From_Slug( Session, Match_Slug )

        StatsApi_Data = None

        try:
            StatsApi_Data = Resolve_Match_From_StatsApi(
                Session = Session,
                Match_Id = Match_Id,
            )
        except RuntimeError as Error:
            print( f"WARNING: {Error}", file = sys.stderr )

        if SportApi_Data is None:
            try:
                SportApi_Data = Resolve_Match_From_Id(
                    Session = Session,
                    Match_Id = Match_Id,
                )
            except RuntimeError as Error:
                print( f"WARNING: {Error}", file = sys.stderr )
                SportApi_Data = None

        if ( StatsApi_Data is None ) and ( SportApi_Data is None ):
            raise RuntimeError(
                f"Could not resolve match [{Match_Id}] from StatsAPI or SportAPI. "
                "The match id may be valid, but match data may not be published yet."
            )

        Resolved_Metadata = Build_Resolved_Metadata(
            Match_Id = Match_Id,
            Match_Slug = Match_Slug,
            Dapi_Data = Dapi_Data,
            SportApi_Data = SportApi_Data,
            StatsApi_Data = StatsApi_Data,
        )

        Endpoints = Build_Endpoint_List(
            Match_Id = Match_Id,
            Match_Slug = Match_Slug,
            Season_Id = Resolved_Metadata.get( "Season_Id" ),
            Competition_Id = Resolved_Metadata.get( "Competition_Id" ),
            Home_Team_Id = Resolved_Metadata.get( "Home_Team_Id" ),
            Away_Team_Id = Resolved_Metadata.get( "Away_Team_Id" ),
            Home_Team = Resolved_Metadata.get( "Home_Team" ),
            Away_Team = Resolved_Metadata.get( "Away_Team" ),
            Match_Date = Resolved_Metadata.get( "Match_Date" ),
        )

        Match_Folder_Name = Build_Match_Folder_Name( Resolved_Metadata )
        Match_Output_Directory = Path( Arguments.output ) / Match_Folder_Name
        Match_Output_Directory.mkdir( parents = True, exist_ok = True )

        Save_Response( Match_Output_Directory / "Resolved_Dapi.json", Dapi_Data )

        if SportApi_Data is not None:
            Save_Response( Match_Output_Directory / "Resolved_SportApi.json", SportApi_Data )

        if StatsApi_Data is not None:
            Save_Response( Match_Output_Directory / "StatsApi_Match.json", StatsApi_Data )

            Match_Metadata = Build_Match_Metadata(
                Match_Id = Match_Id,
                Match_Slug = Match_Slug,
                StatsApi_Data = StatsApi_Data,
            )

            Save_Response( Match_Output_Directory / "Match_Metadata.json", Match_Metadata )
        else:
            Download_Error = {
                "Match_Id": Match_Id,
                "Match_Slug": Match_Slug,
                "Error": "StatsAPI match data is not available.",
                "Message": "The match id may be valid, but StatsAPI has not published match data yet.",
            }

            #Save_Response( Match_Output_Directory / "Download_Error.json", Download_Error )

        Download_Summary = Download_All_Endpoints(
            Session = Session,
            Endpoints = Endpoints,
            Output_Directory = Match_Output_Directory,
        )

        Season_Match_Window_File = Match_Output_Directory / "Season_Match_Window.json"

        if ( Season_Match_Window_File.exists() ):

            with Season_Match_Window_File.open( "r", encoding = "utf-8" ) as File_Handle:
                Season_Match_Window_Data = json.load( File_Handle )

            Resolved_Metadata = Build_Resolved_Metadata(
                Match_Id = Match_Id,
                Match_Slug = Match_Slug,
                Dapi_Data = Dapi_Data,
                SportApi_Data = SportApi_Data,
                StatsApi_Data = StatsApi_Data,
                Season_Match_Window_Data = Season_Match_Window_Data,
            )

        Generate_Rosters_CSV(
            Match_Output_Directory = Match_Output_Directory,
        )

        Commentary_Success, Commentary_Data, Commentary_Page_Count, Commentary_Duplicate_Count, Commentary_Status_Code, Commentary_Error_Data = Download_All_Commentary(
            Session = Session,
            Match_Id = Match_Id,
        )

        if Commentary_Success:
            Save_Response( Match_Output_Directory / "Commentary.json", Commentary_Data )

            Download_Summary[ "Downloaded" ][ "Commentary" ] = {
                "Url": f"https://stats-api.mlssoccer.com/matches/{Match_Id}/commentary?language=en",
                "Status_Code": Commentary_Status_Code,
                "Content_Type": "application/json",
                "Output_File": str( Match_Output_Directory / "Commentary.json" ),
                "Pages_Downloaded": Commentary_Page_Count,
                "Commentary_Items": len( Commentary_Data.get( "commentary", [] ) ),
                "Commentary_Duplicates_Skipped": Commentary_Duplicate_Count,
            }
        else:
            Commentary_Error_File = Match_Output_Directory / "Commentary.error.json"
            #Save_Response( Commentary_Error_File, Commentary_Error_Data )

            if "Skipped" not in Download_Summary:
                Download_Summary[ "Skipped" ] = {}

            Download_Summary[ "Skipped" ][ "Commentary" ] = {
                "Url": f"https://stats-api.mlssoccer.com/matches/{Match_Id}/commentary?language=en",
                "Status_Code": Commentary_Status_Code,
                "Output_File": str( Commentary_Error_File ),
                "Pages_Downloaded": Commentary_Page_Count,
                "Commentary_Duplicates_Skipped": Commentary_Duplicate_Count,
            }

        Manifest = {
            "Resolved_Metadata": Resolved_Metadata,
            "Endpoints": Endpoints,
            "Download_Summary": Download_Summary,
        }

        Save_Response( Match_Output_Directory / "Manifest.json", Manifest )
        Generate_GameDay_Availability_Report( Match_Output_Directory, Resolved_Metadata )
        Generate_Match_Lineup_JSON( Match_Output_Directory = Match_Output_Directory )

        print()
        print( f"Match_Id:                    {Match_Id}" )
        print( f"Match_Slug:                  {Match_Slug}" )
        print( f"Venue_Name:                  {Resolved_Metadata.get( 'Venue_Name' )}" )
        print( f"Venue_City:                  {Resolved_Metadata.get( 'Venue_City' )}" )
        print( f"Commentary_Pages:            {Commentary_Page_Count}" )
        print( f"Commentary_Events:           {len( Commentary_Data.get( 'commentary', [] ) )}" )
        print( f"Commentary_Duplicates:       {Commentary_Duplicate_Count}" )
        print( f"Output:                      {Match_Output_Directory}" )

        Failed_Count = len( Download_Summary.get( "Failed", {} ) )
        Skipped_Count = len( Download_Summary.get( "Skipped", {} ) )

        if ( Failed_Count > 0 ) or ( Skipped_Count > 0 ):
            print(
                f"ERROR: Download completed with Failed={Failed_Count}, Skipped={Skipped_Count}",
                file = sys.stderr,
            )

            if Failed_Count > 0:
                print( "", file = sys.stderr )
                print( "Failed endpoints:", file = sys.stderr )

                for Endpoint_Name, Endpoint_Data in Download_Summary.get( "Failed", {} ).items():
                    print(
                        f"  - {Endpoint_Name}: "
                        f"Status={Endpoint_Data.get( 'Status_Code' )} "
                        f"Url={Endpoint_Data.get( 'Url' )}",
                        file = sys.stderr,
                    )

            if Skipped_Count > 0:
                print( "", file = sys.stderr )
                print( "Skipped endpoints:", file = sys.stderr )

                for Endpoint_Name, Endpoint_Data in Download_Summary.get( "Skipped", {} ).items():
                    print(
                        f"  - {Endpoint_Name}: "
                        f"Status={Endpoint_Data.get( 'Status_Code' )} "
                        f"Url={Endpoint_Data.get( 'Url' )}",
                        file = sys.stderr,
                    )

            print( "", file = sys.stderr )
            print( f"Manifest: {Match_Output_Directory / 'Manifest.json'}", file = sys.stderr )

            return 2

        return 0

    except Exception as Error:
        print( f"ERROR: {Error}", file = sys.stderr )
        return 1


if __name__ == "__main__":
    raise SystemExit( Main() )