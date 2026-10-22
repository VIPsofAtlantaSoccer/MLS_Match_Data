#---------------------------------------------------------------------------------------------------------------#
# Outside Requirements
#---------------------------------------------------------------------------------------------------------------#
# pip install requests
#
# Example Usage:
# python Get_MLS_Game_Links.py -url "https://www.mlssoccer.com/clubs/atlanta-united/schedule/#competition=all&date=2025-01-01"
#---------------------------------------------------------------------------------------------------------------#

import argparse
import csv
import os
import re
import sys
import json
from typing import Any, Dict, List, Optional, Tuple
import requests

#---------------------------------------------------------------------------------------------------------------#
# Debug Utility: Save outputs to a local Debug folder for inspection
#---------------------------------------------------------------------------------------------------------------#
DEBUG_DIR = "Debug"

def Save_Debug_File(Filename: str, Data: Any) -> None:
    if not os.path.exists(DEBUG_DIR):
        os.makedirs(DEBUG_DIR)
        
    File_Path = os.path.join(DEBUG_DIR, Filename)
    try:
        with open(File_Path, "w", encoding="utf-8") as File_Handle:
            if isinstance(Data, (dict, list)):
                json.dump(Data, File_Handle, indent=4, ensure_ascii=False)
            else:
                File_Handle.write(str(Data))
        print(f"[DEBUG-LOG] Wrote inspection file: {File_Path}")
    except Exception as Error:
        print(f"[ERROR] Failed to write debug file {Filename}: {Error}", file=sys.stderr)

#---------------------------------------------------------------------------------------------------------------#
# Extract parameters from the incoming schedule hash URL
# Returns a tuple: (Year_String, Club_Slug)
#---------------------------------------------------------------------------------------------------------------#
def Parse_Target_Context( URL: str ) -> Tuple[Optional[str], Optional[str]]:
    Year_Match = re.search( r"date=(\d{4 atmospheric_id}|-\d{4})", URL ) or re.search( r"date=(\d{4})", URL )
    Requested_Year = Year_Match.group( 1 ) if Year_Match else None

    Club_Match = re.search( r"/clubs/([^/]+)/", URL )
    Club_Slug = Club_Match.group( 1 ) if Club_Match else None

    return Requested_Year, Club_Slug

#---------------------------------------------------------------------------------------------------------------#
# Recursively inspect vocabulary records to collect all candidate season IDs for the target year
#---------------------------------------------------------------------------------------------------------------#
def Collect_Season_Candidates( Data: Any, Target_Year: str, Candidates: List[Dict[str, Any]] ) -> None:
    if isinstance( Data, dict ):
        Has_Year = False
        Season_Id = None
        Full_Text = ""
        for Key, Value in Data.items():
            Value_Str = str( Value )
            Full_Text += " " + Value_Str.lower()
            if Target_Year in Value_Str:
                Has_Year = True
            if isinstance( Value, str ) and Value.startswith( "MLS-SEA-" ):
                Season_Id = Value
        if Has_Year and Season_Id:
            Candidates.append( { "Id": Season_Id, "Text": Full_Text } )
            
        for Value in Data.values():
            Collect_Season_Candidates( Value, Target_Year, Candidates )
            
    elif isinstance( Data, list ):
        for Item in Data:
            Collect_Season_Candidates( Item, Target_Year, Candidates )

#---------------------------------------------------------------------------------------------------------------#
# Resolve the internal Sportec Season ID variable via global vocabulary tables
#---------------------------------------------------------------------------------------------------------------#
def Resolve_Season_Id_From_Vocabs( Target_Year: str ) -> Optional[str]:
    print( f"[DEBUG] Contacting global vocabs directory to isolate the {Target_Year} season token..." )
    Url = "https://www.mlssoccer.com/vocabs/en"
    
    try:
        Response = requests.get( Url, headers={ "User-Agent": "Mozilla/5.0" }, timeout=15 )
        if Response.status_code != 200:
            print( f"[WARNING] Main vocabs directory returned {Response.status_code}. Trying DAPI layer...", file=sys.stderr )
            Url = "https://dapi.mlssoccer.com/v2/content/en-us/vocabs/en"
            Response = requests.get( Url, headers={ "User-Agent": "Mozilla/5.0" }, timeout=15 )
            
        if Response.status_code == 200:
            try:
                Payload = Response.json()
                Save_Debug_File("Vocab_Response_Raw.json", Payload)
            except ValueError:
                Save_Debug_File("Vocab_Response_Raw.txt", Response.text)
                print( "[ERROR] Received non-JSON response from vocabs endpoint.", file=sys.stderr )
                return None

            Candidates = []
            Collect_Season_Candidates( Payload, Target_Year, Candidates )
            
            # Dump the list of matched candidates to see what the recursive search actually found
            Save_Debug_File("Vocab_Candidates.json", Candidates)
            
            # Filter candidates to isolate the main MLS Regular Season structure
            if Candidates:
                for Cand in Candidates:
                    if "regular" in Cand["Text"] and "mls" in Cand["Text"]:
                        return Cand["Id"]
                for Cand in Candidates:
                    if "regular" in Cand["Text"]:
                        return Cand["Id"]
                return Candidates[0]["Id"]
                
            # Regex backup strategy directly on the raw text stream
            Text_Matches = re.findall( r"MLS-SEA-[A-Z0-9]+", Response.text )
            if Text_Matches:
                return Text_Matches[0]
                
    except Exception as Error:
        print( f"[ERROR] Vocabulary resolution error: {Error}", file=sys.stderr )
        
    return None

#---------------------------------------------------------------------------------------------------------------#
# Fetch all matches for the resolved season token and filter by club text fields
#---------------------------------------------------------------------------------------------------------------#
def Fetch_Schedule_Via_Season( Season_Id: str, Target_Year: str, Club_Slug: str ) -> List[Dict[str, str]]:
    print( f"[DEBUG] Requesting season match matrix using validated token: {Season_Id}..." )
    
    # Query with a large per_page allocation to pull down the schedule cleanly in a single operation
    Url = f"https://stats-api.mlssoccer.com/matches/seasons/{Season_Id}?per_page=1000&sort=planned_kickoff_time:asc"
    Game_Links = []
    
    Search_Term = Club_Slug.lower()
    Short_Term = Club_Slug.split('-')[0].lower()  # e.g., "atlanta"
    
    try:
        Response = requests.get( Url, headers={ "User-Agent": "Mozilla/5.0" }, timeout=15 )
        if Response.status_code != 200:
            print( f"[ERROR] Season match registry returned code {Response.status_code}", file=sys.stderr )
            return []
            
        Payload = Response.json()
        Save_Debug_File("Match_Matrix_Raw.json", Payload)

        Matches = []
        if isinstance( Payload, list ):
            Matches = Payload
        elif isinstance( Payload, dict ):
            Matches = Payload.get( "matches", [] )
            
        print( f"[DEBUG] Scanning {len(Matches)} total league matches for '{Club_Slug}' involvement..." )
        
        for Match in Matches:
            Slug = Match.get( "slug" )
            if not Slug:
                continue
                
            Home_Slug = Match.get( "home", {} ).get( "slug", "" ).lower()
            Away_Slug = Match.get( "away", {} ).get( "slug", "" ).lower()
            Home_Name = Match.get( "home", {} ).get( "fullName", "" ).lower()
            Away_Name = Match.get( "away", {} ).get( "fullName", "" ).lower()
            
            # Robust verification to capture structural slug shifts across years
            Is_Home = ( Search_Term in Home_Slug ) or ( Short_Term in Home_Slug ) or ( Search_Term in Home_Name )
            Is_Away = ( Search_Term in Away_Slug ) or ( Short_Term in Away_Slug ) or ( Search_Term in Away_Name )
            
            if not ( Is_Home or Is_Away ):
                continue
                
            Comp_Slug = Match.get( "competition", {} ).get( "slug", "mls-regular-season" )
            Full_Url = f"https://www.mlssoccer.com/competitions/{Comp_Slug}/{Target_Year}/matches/{Slug}"
            
            Home_Team = Match.get( "home", {} ).get( "fullName", "Unknown Home" )
            Away_Team = Match.get( "away", {} ).get( "fullName", "Unknown Away" )
            
            Game_Links.append({
                "URL": Full_Url,
                "Text": f"{Home_Team} vs {Away_Team}"
            })
            
    except Exception as Error:
        print( f"[ERROR] Failure reading season matches: {Error}", file=sys.stderr )
        
    return Game_Links

#---------------------------------------------------------------------------------------------------------------#
# Write game links to a CSV file (Maintains your duplicate resolution strategy)
#---------------------------------------------------------------------------------------------------------------#
def Write_Game_Links( Game_Links: List[Dict[str, str]], Output_File: str ) -> None:
    Combined_Links = {}
    Existing_Rows = []

    if os.path.exists( Output_File ):
        with open( Output_File, "r", newline="", encoding="utf-8" ) as File_Handle:
            Reader = csv.DictReader( File_Handle )
            for Row in Reader:
                URL = Row.get( "URL", "" ).strip()
                if not URL:
                    continue
                Existing_Rows.append({
                    "URL": URL,
                    "Text": Row.get( "Text", "" ).strip()
                })

    for Existing_Row in Existing_Rows:
        Combined_Links[ Existing_Row["URL"] ] = Existing_Row

    for Game_Link in Game_Links:
        Combined_Links[ Game_Link["URL"] ] = Game_Link

    Sorted_Links = sorted( Combined_Links.values(), key=lambda Item: Item["URL"] )

    with open( Output_File, "w", newline="", encoding="utf-8" ) as File_Handle:
        Writer = csv.DictWriter( File_Handle, fieldnames=[ "URL", "Text" ] )
        Writer.writeheader()
        for Game_Link in Sorted_Links:
            Writer.writerow( Game_Link )

    print( f"[DEBUG] Saved {len( Sorted_Links )} unique game links to '{Output_File}'" )

#---------------------------------------------------------------------------------------------------------------#
# Application Entry Point
#--------------------------------------------------------------------------------#
def Main():
    Parser = argparse.ArgumentParser(description="API-based MLS schedule processing engine.")
    Parser.add_argument("-url", required=True, help="MLS schedule URL containing target directives")
    Parser.add_argument("-output", default="MLS_Game_Links.csv", help="Output CSV file path")
    Args = Parser.parse_args()

    Target_Year, Club_Slug = Parse_Target_Context( Args.url )
    if not Target_Year or not Club_Slug:
        print("[ERROR] URL format invalid. Must include a club slug and a '#date=YYYY-MM-DD' token.", file=sys.stderr)
        return 1

    print(f"--- INITIALIZING DATA ENGINE ---")
    print(f"Target Year: {Target_Year}")
    print(f"Target Club: {Club_Slug}")

    # Discover the validated season token via the public vocabulary directory
    Season_Id = Resolve_Season_Id_From_Vocabs( Target_Year )
    if not Season_Id:
        print(f"[ERROR] Could not isolate a season registry record for year {Target_Year}.", file=sys.stderr)
        return 1
        
    print(f"[DEBUG] Successfully resolved Season ID: {Season_Id}")

    # Fetch matches cleanly using the resolved structural route token
    Game_Links = Fetch_Schedule_Via_Season( Season_Id, Target_Year, Club_Slug )
    
    if not Game_Links:
        print(f"[DEBUG] No games found matching your criteria.")
        return 0

    # Update CSV record collection
    Write_Game_Links( Game_Links, Args.output )
    print(f"Success. Finished extracting matches via pure data API layers.\n")
    return 0

if __name__ == "__main__":
    sys.exit( Main() )