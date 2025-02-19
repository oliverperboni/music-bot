from database import SessionLocal
from models import Playlist, PlaylistEntry


def process_and_store_playlist(info, playlist_name):  
    """Processes playlist info and stores it in the database."""
    db = SessionLocal()  
    try:
        playlist = db.query(Playlist).filter(Playlist.name == playlist_name).first() 
        if not playlist:
            playlist = Playlist(name=playlist_name)
            db.add(playlist)
            db.commit()
            db.refresh(playlist)

        entries_to_add = []
        if "entries" in info:
            for entry in info["entries"]:
                playlist_entry = PlaylistEntry(
                    url=entry["url"],
                    title=entry.get("title", "Unknown Title"),
                    thumbnail=entry.get("thumbnail", None),
                    duration=entry.get("duration", 0),
                    channel=entry.get("uploader", "Unknown Channel"),
                    playlist_id=playlist.id  
                )
                entries_to_add.append(playlist_entry)
        else:
            playlist_entry = PlaylistEntry(
                url=info["url"],
                title=info.get("title", "Unknown Title"),
                thumbnail=info.get("thumbnail", None),
                duration=info.get("duration", 0),
                channel=info.get("uploader", "Unknown Channel"),
                playlist_id=playlist.id  
            )
            entries_to_add.append(playlist_entry)

        db.add_all(entries_to_add)
        db.commit()
    except Exception as e:
        db.rollback()  
        print(f"An error occurred: {e}") 
        raise 
    finally:
        db.close()  #



def get_playlist_entries(playlist_name):
    db = SessionLocal()
    try:
        playlist = db.query(Playlist).filter(Playlist.name == playlist_name).first()
        if playlist:
            entries = db.query(PlaylistEntry).filter(PlaylistEntry.playlist_id == playlist.id).all()
            return entries
        else:
            return None
    finally:
        db.close()
