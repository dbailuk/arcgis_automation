from arcgis.gis import GIS

gis = GIS("https://gis.czu.cz/portal", client_id="", allow_jupyter_auth=True)
print("Logged in as:", gis.users.me)
print(gis._con.token)

#Third part libraries need to be installed(copy and insert into the terminal)
#pip install reportlab
#pip install arcgis argparse
