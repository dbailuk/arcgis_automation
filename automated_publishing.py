import os
import sys
import time
import logging
import webbrowser
from arcgis.gis import GIS
from arcgis.features import FeatureLayerCollection

# Configuration settings for connecting to the ArcGIS Portal and for service publishing
PORTAL_URL = "https://gis.czu.cz/portal"
TOKEN = ""

# The CONFIG dictionary holds various configuration parameters
CONFIG = {
	"log_file": "logs_reports/arcgis_publish_log.txt",
	"arcgis": {
		"shapefile": ".shp",
		"service_name": ""
	},
	"metadata": {
		"description": "Service published using configuration settings.",
		"tags": "configured,arcgis,service",
		"categories": "Example"
	},
	"default_share_level": "org"
}

# Ensure that the logs_reports folder exists; if not, create it.
if not os.path.exists("logs_reports"):
	os.makedirs("logs_reports")

# Connect to the ArcGIS Portal using the provided URL and token.
try:
	gis = GIS(PORTAL_URL, token=TOKEN)
	print(f"✅ Connected to ArcGIS Portal as {gis.users.me.username}")
except Exception as e:
	print(f"❌ Failed to connect: {e}")
	sys.exit()

# Setup logging to record events and errors in a log file.
logging.basicConfig(
	filename=CONFIG["log_file"],
	level=logging.INFO,
	format="%(asctime)s - %(levelname)s - %(message)s"
)

# Delete any existing feature service that exactly matches the given service name.
def delete_existing_service(service_name):
	# Build a query to search for the service by title and owner.
	query = f'title:"{service_name}" AND owner:{gis.users.me.username}'
	# Perform the search for Feature Services.
	search_results = gis.content.search(query=query, item_type="Feature Service", max_items=10)
	if search_results:
		# Iterate over found items and delete each.
		for item in search_results:
			try:
				item.delete()
				print(f"🗑️ Deleted existing service: {item.title}")
				logging.info(f"Deleted existing service: {item.title}")
			except Exception as e:
				print(f"❌ Error deleting service {item.title}: {e}")
				logging.error(f"Error deleting service {item.title}: {e}")
				return False
	return True

# Wait until the service is completely deleted, or until a timeout is reached.
def wait_for_service_deletion(service_name, timeout=180):
	"""
	Waits until no feature service with the given title exists.
	Returns True if deletion is confirmed within the timeout period, otherwise returns False.
	"""
	start_time = time.time()
	query = f'title:"{service_name}" AND owner:{gis.users.me.username}'
	# Continuously check until the service is deleted or the timeout expires.
	while time.time() - start_time < timeout:
		search_results = gis.content.search(query=query, item_type="Feature Service", max_items=1)
		if not search_results:
			return True
		print(f"Waiting for service '{service_name}' to be fully deleted...")
		time.sleep(5)
	return False

# Search for items of a given file type owned by the current user.
def get_portal_files(file_types=["Shapefile"]):
	"""
	Searches portal content for items of the specified types owned by the current user.
	Returns a list of matching items.
	"""
	items = []
	username = gis.users.me.username
	# Loop through each specified file type.
	for ftype in file_types:
		results = gis.content.search(query=f'type:"{ftype}" AND owner:{username}', max_items=100)
		items.extend(results)
	return items

# Function: interactive_selection
# Purpose: Let the user select which items to publish from a displayed list.
def interactive_selection(options):
	"""
	Presents a numbered list of options and returns the selected items.
	"""
	if not options:
		return []
	print("\nDiscovered items:")
	# Display each discovered item with an index.
	for idx, opt in enumerate(options):
		print(f"[{idx}] {opt.title} ({opt.type})")
	# Prompt user to choose indices or type 'all' to select every item.
	choice = input("Enter the indices to publish (e.g., 0,2,3) or 'all': ").strip()
	if choice.lower() == "all":
		return options
	else:
		try:
			# Convert the comma-separated string into a list of indices.
			indices = [int(x.strip()) for x in choice.split(",")]
			return [options[i] for i in indices if i < len(options)]
		except Exception:
			print("Invalid input. Publishing all discovered items.")
			return options

# Function: get_user_metadata
# Purpose: Retrieve metadata settings from the CONFIG dictionary.
def get_user_metadata():
	"""
	Returns metadata for the service from the configuration.
	"""
	return CONFIG.get("metadata", {"description": "", "tags": "", "categories": ""})

# Function: publish_feature_service
# Purpose: Publish an item as a feature service, update its metadata, and return the published item.
def publish_feature_service(item, service_name, metadata):
	"""
	Publishes the provided item as a feature service with the given service name.
	Updates metadata after publishing.
	Returns the published item or None if publishing fails.
	"""
	try:
		logging.info(f"Attempting to publish item: {item.title}")
		print(f"✅ Uploading {item.title}...")
		# Publish the item with the provided service name.
		published_item = item.publish(publish_parameters={'name': service_name})
		if published_item is None:
			raise Exception("Publishing returned None")
		print(f"✅ Published Feature Service: {published_item.title}")
		logging.info(f"Published Feature Service: {published_item.title}")
		# Update the service metadata: tags, description, and categories.
		published_item.update({
			"tags": metadata.get("tags", ""),
			"description": metadata.get("description", ""),
			"categories": metadata.get("categories", "")
		})
		print(f"✅ Updated metadata for {published_item.title}")
		logging.info(f"Updated metadata for {published_item.title}")
		return published_item
	except Exception as e:
		logging.error(f"Failed to publish service: {e}")
		print(f"❌ Failed to publish service: {e}")
		return None

# Retrieve portal items of type "Shapefile" (excluding File Geodatabases)
discovered_items = get_portal_files(file_types=["Shapefile"])
if not discovered_items:
	print("No matching items found in your portal content.")
	sys.exit()

# Let the user select which discovered items should be published
selected_items = interactive_selection(discovered_items)
print("\nSelected items to publish:")
for idx, itm in enumerate(selected_items):
	print(f"[{idx}] {itm.title} ({itm.type})")

# List to store successfully published services
published_services = []
single_publish = (len(selected_items) == 1)

# Process each selected item for publishing
for itm in selected_items:
	# Determine the service name and metadata based on whether there is only one selected item.
	if single_publish:
		service_name = CONFIG["arcgis"].get("service_name", os.path.splitext(itm.title)[0])
		metadata = get_user_metadata()
	else:
		service_name = os.path.splitext(itm.title)[0]
		metadata = {}

	# Check if a service with the same name already exists and delete it if found.
	existing = gis.content.search(
		query=f'title:"{service_name}" AND owner:{gis.users.me.username}', item_type="Feature Service", max_items=1
	)
	if existing:
		print(f"⚠️ Service '{service_name}' already exists. Deleting it automatically...")
		if delete_existing_service(service_name):
			if not wait_for_service_deletion(service_name):
				print(f"❌ Timeout waiting for deletion of '{service_name}'. Skipping this item.")
				continue
		else:
			print(f"❌ Could not delete existing service '{service_name}'. Skipping this item.")
			continue

	# Publish the selected item as a feature service.
	fs = publish_feature_service(itm, service_name, metadata)
	if fs is None:
		# If a conflict occurs, attempt deletion and republishing.
		print(f"⚠️ Conflict detected for '{service_name}'. Attempting to delete and republish...")
		if delete_existing_service(service_name):
			if wait_for_service_deletion(service_name):
				fs = publish_feature_service(itm, service_name, metadata)
			else:
				print(f"❌ Timeout waiting for deletion of '{service_name}'. Skipping this item.")
				continue
		else:
			print(f"❌ Could not delete existing service '{service_name}'. Skipping this item.")
			continue

	# If publishing was successful, update the service's properties and sharing permissions.
	if fs:
		try:
			# Update the feature layer properties of the published service.
			layers = FeatureLayerCollection(fs.url, gis)
			layers.manager.update_definition({
				"capabilities": "Query, Editing, Extract",
				"maxRecordCount": 5000,
				"allowGeometryUpdates": True
			})
			print(f"✅ Service properties updated for {fs.title}")
			logging.info(f"Service properties updated for {fs.title}")
		except Exception as e:
			print(f"❌ Failed to update service properties: {e}")
			logging.error(f"Failed to update service properties for {fs.title}: {e}")

		# Set sharing permissions based on the default share level in the configuration.
		share_level = CONFIG.get("default_share_level", "org")
		try:
			if share_level == "public":
				fs.share(everyone=True, org=False)
			elif share_level == "org":
				fs.share(everyone=False, org=True)
			else:
				fs.share(everyone=False, org=False)
			print(f"✅ Permissions set to {share_level} for {fs.title}")
			logging.info(f"Permissions set to {share_level} for {fs.title}")
		except Exception as e:
			print(f"❌ Failed to set permissions: {e}")
			logging.error(f"Failed to set permissions for {fs.title}: {e}")

		published_services.append(fs)
	else:
		print(f"❌ Failed to publish {service_name}")

# Offer the user an option to preview each published service in the ArcGIS Online Map Viewer.
for service in published_services:
	preview_choice = input(f"Do you want to preview the map for {service.title}? (y/n): ").strip().lower()
	if preview_choice == "y":
		try:
			map_viewer_url = f"https://www.arcgis.com/apps/mapviewer/index.html?url={service.url}&source=sd"
			webbrowser.open(map_viewer_url)
			print(f"🔍 Opening map preview: {map_viewer_url}")
		except Exception as e:
			print(f"❌ Failed to open map preview: {e}")
			logging.error(f"Failed to open map preview for {service.title}: {e}")

print("🚀 Publishing process completed.")
