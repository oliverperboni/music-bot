
from database import Base
from sqlalchemy import create_engine, Column, Integer, String, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

class Playlist(Base):
    __tablename__ = "playlists"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)  # Add a name for the playlist
    entries = relationship("PlaylistEntry", back_populates="playlist")

# Define the PlaylistEntry model
class PlaylistEntry(Base):
    __tablename__ = "playlist_entries"

    id = Column(Integer, primary_key=True, index=True)
    url = Column(String, index=True)
    title = Column(String, nullable=True)
    thumbnail = Column(String, nullable=True)
    duration = Column(Integer, nullable=True)
    channel = Column(String, nullable=True)
    playlist_id = Column(Integer, ForeignKey("playlists.id")) 
    playlist = relationship("Playlist", back_populates="entries")