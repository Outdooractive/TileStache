""" Support for MySQL databases in MBTiles format.

MBTiles (http://mbtiles.org) is a specification for storing tiled map data in
SQLite databases for immediate use and for transfer. The databases are designed for
portability of thousands, hundreds of thousands, or even millions of standard
map tile images in a single database.

This makes it easy to manage and share map tiles.

Read the spec:
    https://github.com/mapbox/mbtiles-spec/blob/master/1.1/spec.md

Example configuration:

  {
    "cache": { ... }.
    "layers":
    {
      "roads":
      {
        "provider":
        {
          "name": "postgres",
          "tileset": "host=localhost dbname=mbtiles user=testuser password=testpassword"
        }
      }
    }
  }

MySQL provider parameters:

  tileset:
    Required MySQL connect string.
"""
import logging
from urlparse import urlparse, urljoin

import sqlalchemy.pool as pool
import oursql

from ModestMaps.Core import Coordinate


class Provider:
    """ MBTiles provider.
    
        See module documentation for explanation of constructor arguments.
    """

    def getconn(self):
        c = oursql.connect(host=self.connect_options['host'], user=self.connect_options['user'], passwd=self.connect_options['password'], db=self.connect_options['dbname'], raise_on_warnings=False)
        return c

    def __init__(self, layer, tileset):
        """
        """        
        if tileset.find("dbname") < 0:
            raise Exception('Bad scheme in MySQL provider, must be a MySQL connect string: "%s"' % tileset)
        
        self.connect_options = dict(option.split("=") for option in tileset.split(" "))
        self.layer = layer
        self.flip_y = True

        #self.database = pool.QueuePool(self.getconn, max_overflow=1, pool_size=1)

        #db = self.database.connect()
        db = self.getconn()
        cursor = db.cursor()

        formats = {'png': 'image/png', 'jpg': 'image/jpeg', None: None}

	try:
            cursor.execute("SELECT value FROM metadata WHERE name='format'")
            format = cursor.fetchone()
            format = format and format[0] or None
            self.mime_type = formats[format]
        except:
            self.mime_type = 'image/png'
            #raise Exception("Bad tileset '%s'" % (tileset,))

        db.close()

    @staticmethod
    def prepareKeywordArgs(config_dict):
        """ Convert configured parameters to keyword args for __init__().
        """
        return {'tileset': config_dict['tileset']}
    
    def renderTile(self, width, height, srs, coord, tile_scale):
        """ Retrieve a single tile, return a TileResponse instance.
        """
        #db = self.database.connect()
        db = self.getconn()
        cursor = db.cursor()

        tile_zoom = coord.zoom
        tile_column = coord.column
        tile_row = coord.row
        if self.flip_y:
            tile_row = (2**coord.zoom - 1) - coord.row # Hello, Paul Ramsey.

	#logging.info("SELECT tile_data FROM tiles WHERE zoom_level=%d AND tile_column=%d AND tile_row=%d AND tile_scale=%d" % (tile_zoom, tile_column, tile_row, tile_scale))

        cursor.execute('SELECT tile_data FROM tiles WHERE zoom_level=? AND tile_column=? AND tile_row=? AND tile_scale=?',
            (tile_zoom, tile_column, tile_row, tile_scale))
        content = cursor.fetchone()
        content = content and content[0] or None

        db.close()

        formats = {'image/png': 'PNG', 'image/jpeg': 'JPEG', None: None}
        return TileResponse(formats[self.mime_type], content)

    def tileMetadata(self, coord):
        """ Retrieve metadata for a single tile, return a json-like object.
        """
        #db = self.database.connect()
        db = self.getconn()
        cursor = db.cursor()

        tile_row = coord.row
        if self.flip_y:
            tile_row = (2**coord.zoom - 1) - coord.row # Hello, Paul Ramsey.
        cursor.execute('SELECT updated_at FROM tiles WHERE zoom_level=? AND tile_column=? AND tile_row=?',
            (coord.zoom, coord.column, tile_row))
        content = cursor.fetchone()
        content = content and content[0] or None

        db.close()

        return "{\"updated_at\": %d, \"zoom\": %d, \"x\": %d, \"y\": %d}" % (content, coord.zoom, coord.column, tile_row)

    def getTypeByExtension(self, extension):
        """ Get mime-type and PIL format by file extension.
        """
        if extension.lower() == 'meta':
            return 'text/plain', None

        elif extension.lower() == 'png':
            return 'image/png', 'PNG'

        elif extension.lower() == 'jpg':
            return 'image/jpeg', 'JPEG'

        else:
            raise KnownUnknown('Unknown extension in configuration: "%s"' % extension)


class TileResponse:
    """ Wrapper class for tile response that makes it behave like a PIL.Image object.
    
        TileStache.getTile() expects to be able to save one of these to a buffer.
        
        Constructor arguments:
        - format: 'PNG' or 'JPEG'.
        - content: Raw response bytes.
    """
    def __init__(self, format, content):
        self.format = format
        self.content = content
    
    def save(self, out, format):
        if self.format is not None and format != self.format:
            raise Exception('Requested format "%s" does not match tileset format "%s"' % (format, self.format))

        out.write(self.content)
