
#---------------------------------------------------------------------------------------------------------------#
# MLS API
#
# Handle MLS API requests, match identification, endpoint downloads, and schedule discovery.
#---------------------------------------------------------------------------------------------------------------#
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import requests
from rich import print
from rich.table import Table


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

    Endpoints[ "Club_Possession" ] = f"https://stats-api.mlssoccer.com/statistics/clubs/matches/{Match_Id}/possession?scope=all"
    Endpoints[ "Player_Statistics" ] = f"https://stats-api.mlssoccer.com/statistics/players/matches/{Match_Id}?per_page=200"

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
        "Unavailable": {},
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
        elif ( Endpoint_Name == "Club_Possession" and Status_Code == 404 ):
            Record[ "Output_File" ] = None
            Summary[ "Unavailable" ][ Endpoint_Name ] = Record

            Results_Table.add_row(
                Endpoint_Name,
                "[yellow]Unavailable[/]",
                str( Status_Code ),
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

