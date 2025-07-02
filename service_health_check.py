import requests
import logging
import smtplib
import time
import datetime
import os
from email.message import EmailMessage
from arcgis.gis import GIS
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter

# Create the "logs_reports" folder if it doesn't exist
if not os.path.exists("logs_reports"):
	os.makedirs("logs_reports")

# Load the saved token for authentication to ArcGIS Portal
saved_token = ""

# Configuration dictionary for service endpoints, logging, email and ArcGIS parameters
CONFIG = {
	"websites": [
		{"url": "https://gis.czu.cz/portal", "type": "portal"},
		{"url": "https://gis.czu.cz/serverhs/rest/services", "type": "server"},
		{"url": "https://gis.czu.cz/serverhs/rest/info/healthcheck", "type": "healthcheck"}
	],
	"log_file": "logs_reports/arcgis_health_log.txt",
	"smtp": {
		"server": "smtp.gmail.com",
		"port": 587,
		"username": "",
		"password": "",
		"recipient": ""
	},
	"arcgis": {
		"url": "https://gis.czu.cz/portal",
		"shapefile": "PID"
	}
}

# Setup logging to file with INFO level and a specific format
logging.basicConfig(filename=CONFIG["log_file"], level=logging.INFO,
	format='%(asctime)s - %(levelname)s - %(message)s')


def check_website(url, type_):
	"""
	Checks if a website endpoint is accessible.
	Tracks the response time and checks the response content for the healthcheck endpoint.
	Returns a dictionary with the URL, type, status, response time, and any error encountered.
	"""
	result = {"url": url, "type": type_, "status": None, "response_time": None, "error": ""}
	start = time.perf_counter()
	try:
		response = requests.get(url, timeout=10)
		elapsed = time.perf_counter() - start
		result["response_time"] = elapsed

		if response.status_code == 200:
			# For healthcheck endpoints, verify that the expected content is present
			if type_ == "healthcheck" and "succes" not in response.text.lower():
				result["status"] = "FAIL"
				result["error"] = "Unexpected response content."
				logging.error(f"FAIL: {type_} {url} returned unexpected response content.")
				print(f"FAIL: {type_} {url} returned unexpected response content.")
			else:
				result["status"] = "SUCCESS"
				logging.info(f"SUCCESS: {type_} {url} is accessible.")
				print(f"SUCCESS: {type_} {url} is accessible. Response time: {elapsed:.2f} seconds.")
		else:
			result["status"] = "FAIL"
			result["error"] = f"Status code {response.status_code}"
			logging.error(f"FAIL: {type_} {url} returned status {response.status_code}")
			print(f"FAIL: {type_} {url} returned status code {response.status_code}.")
	except requests.RequestException as e:
		result["response_time"] = time.perf_counter() - start
		result["status"] = "FAIL"
		result["error"] = str(e)
		logging.error(f"ERROR: {type_} {url} is not accessible. {str(e)}")
		print(f"ERROR: {type_} {url} check encountered an error: {str(e)}")

	return result


def publish_test_layer():
	"""
	Publishes a test feature layer from an existing shapefile to verify ArcGIS database connectivity.
	Searches for a shapefile and any existing test layer in the logged-in user's content,
	publishes the shapefile as a feature service, waits briefly, and then deletes it.
	Returns a dictionary with the test status, response time, and any error encountered.
	"""
	result = {"test": "ArcGIS Publishing Test", "status": None, "response_time": None, "error": ""}
	start = time.perf_counter()

	# Use the shapefile name provided in the configuration
	shapefile_name = CONFIG["arcgis"]["shapefile"]

	try:
		# Authenticate to the ArcGIS Portal using the saved token
		gis = GIS(CONFIG["arcgis"]["url"], token=saved_token)
		logging.info("Connected to ArcGIS Portal using saved token.")
		print("SUCCESS: Connected to ArcGIS Portal using saved token.")

		# Restrict content search to the logged-in user's items
		current_user = gis.users.me
		owner_username = current_user.username

		# Delete an existing test layer if it exists (only within the user's content)
		search_results = gis.content.search(
			query=f'title:"{shapefile_name}" AND owner:"{owner_username}"',
			item_type="Feature Service", max_items=1
		)
		if search_results:
			existing_layer = search_results[0]
			logging.info(f"🗑️ Deleting existing test layer: {existing_layer.title}")
			print(f"INFO: Deleting existing test layer: {existing_layer.title}")
			existing_layer.delete()

		# Search for the shapefile item (only within the user's content)
		search_results = gis.content.search(
			query=f'title:"{shapefile_name}" AND owner:"{owner_username}"',
			item_type="Shapefile", max_items=1
		)
		if not search_results:
			result["status"] = "FAIL"
			result["error"] = "Shapefile not found in user content."
			logging.error("Shapefile not found in user content.")
			print("FAIL: Shapefile not found in user content.")
			result["response_time"] = time.perf_counter() - start
			return result

		item = search_results[0]
		logging.info(f"Found shapefile in user content: {item.title}")
		print(f"SUCCESS: Found shapefile in user content: {item.title}")
		# Publish the shapefile as a feature service
		published_item = item.publish()

		if published_item:
			logging.info("Test layer successfully published.")
			print("SUCCESS: Test layer successfully published.")
			time.sleep(5)  # Pause briefly to allow the service to initialize
			published_item.delete()
			logging.info("Test layer deleted successfully.")
			print("SUCCESS: Test layer deleted successfully.")
			result["status"] = "SUCCESS"
		else:
			logging.error("Test layer failed to publish.")
			print("FAIL: Test layer failed to publish.")
			result["status"] = "FAIL"
			result["error"] = "Test layer failed to publish."

		result["response_time"] = time.perf_counter() - start
		return result

	except Exception as e:
		logging.error(f"ERROR: Failed to publish test layer. {str(e)}")
		print(f"ERROR: Failed to publish test layer: {str(e)}")
		result["status"] = "FAIL"
		result["error"] = str(e)
		result["response_time"] = time.perf_counter() - start
		return result


def generate_pdf_report(website_results, arcgis_result):
	"""
	Generates a PDF report of the health-check results using ReportLab.

	The report includes a header, summary statistics (total websites, success/failure counts,
	average response times, and ArcGIS publishing test results), and detailed check results.
	Returns the filename of the generated PDF report.
	"""
	timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
	pdf_filename = f"logs_reports/arcgis_health_report_{timestamp}.pdf"
	c = canvas.Canvas(pdf_filename, pagesize=letter)
	width, height = letter
	margin = 50
	y_position = height - margin

	# Report header
	c.setFont("Helvetica-Bold", 18)
	c.drawCentredString(width / 2, y_position, "ArcGIS Health Check Report")
	y_position -= 40

	# Calculate summary statistics from website results
	total_websites = len(website_results)
	success_count = sum(1 for r in website_results if r["status"] == "SUCCESS")
	fail_count = total_websites - success_count
	successful_times = [r["response_time"] for r in website_results if r["status"] == "SUCCESS" and r["response_time"] is not None]
	avg_response_time = sum(successful_times) / len(successful_times) if successful_times else 0

	# Write summary statistics to the PDF
	c.setFont("Helvetica-Bold", 14)
	c.drawString(margin, y_position, "Summary Statistics:")
	y_position -= 20
	c.setFont("Helvetica", 12)
	summary_lines = [
		f"Total Websites Checked: {total_websites}",
		f"Successful Checks: {success_count}",
		f"Failed Checks: {fail_count}",
		f"Average Response Time (successful sites): {avg_response_time:.2f} seconds",
		f"ArcGIS Publishing Test: {arcgis_result['status']}",
		f"ArcGIS Publishing Test Response Time: {arcgis_result['response_time']:.2f} seconds",
		f"ArcGIS Publishing Test Error: {arcgis_result['error']}" if arcgis_result['error'] else ""
	]
	for line in summary_lines:
		if y_position < margin:
			c.showPage()
			y_position = height - margin
		c.drawString(margin, y_position, line)
		y_position -= 15

	# Write detailed website check results to the PDF
	y_position -= 20
	c.setFont("Helvetica-Bold", 14)
	c.drawString(margin, y_position, "Detailed Website Check Results:")
	y_position -= 20
	c.setFont("Helvetica", 10)
	for r in website_results:
		details = (
			f"URL: {r['url']}, Type: {r['type']}, Status: {r['status']}, "
			f"Response Time: {r['response_time']:.2f} sec"
		)
		if r["error"]:
			details += f", Error: {r['error']}"
		if y_position < margin:
			c.showPage()
			y_position = height - margin
		c.drawString(margin, y_position, details)
		y_position -= 12

	# Save the PDF file
	c.save()
	logging.info(f"PDF report generated: {pdf_filename}")
	print(f"SUCCESS: PDF report generated: {pdf_filename}")
	return pdf_filename


def send_email(subject, message, attachment_path=None):
	"""
	Sends an email notification with PDF attachment.
	This function logs in to the SMTP server using the credentials in the configuration,
	attaches the PDF report if provided, and sends the message.
	"""
	try:
		msg = EmailMessage()
		msg.set_content(message)
		msg["Subject"] = subject
		msg["From"] = CONFIG["smtp"]["username"]
		msg["To"] = CONFIG["smtp"]["recipient"]

		# Attach the PDF report if a valid attachment path is provided
		if attachment_path is not None:
			with open(attachment_path, "rb") as f:
				file_data = f.read()
				file_name = os.path.basename(attachment_path)
			msg.add_attachment(file_data, maintype="application", subtype="pdf", filename=file_name)

		with smtplib.SMTP(CONFIG["smtp"]["server"], CONFIG["smtp"]["port"]) as server:
			server.starttls()
			server.login(CONFIG["smtp"]["username"], CONFIG["smtp"]["password"])
			server.send_message(msg)
			logging.info("Email alert sent successfully.")
			print("SUCCESS: Email alert sent successfully.")
	except Exception as e:
		logging.error(f"ERROR: Failed to send email. {str(e)}")
		print(f"ERROR: Failed to send email: {str(e)}")

# Run website health checks for all configured endpoints
website_results = []
print("Starting website health checks...")
for site in CONFIG["websites"]:
	result = check_website(site["url"], site["type"])
	website_results.append(result)
print("SUCCESS: Website health checks completed.\n")

# Run the ArcGIS Publishing Test
print("Starting ArcGIS publishing test...")
arcgis_result = publish_test_layer()
if arcgis_result["status"] == "SUCCESS":
	print("SUCCESS: ArcGIS publishing test completed.\n")
else:
	print("FAIL: ArcGIS publishing test failed.\n")

# Generate the PDF report from the collected results
print("Generating PDF report...")
pdf_report = generate_pdf_report(website_results, arcgis_result)
print("SUCCESS: PDF report generation completed.\n")

# Determine if any failures occurred in the checks
failures = [r for r in website_results if r["status"] != "SUCCESS"]
if arcgis_result["status"] != "SUCCESS":
	failures.append({"test": "ArcGIS Publishing Test", "error": arcgis_result["error"]})

# Send email notification with the PDF report attached if any failures are found
if failures:
	error_message = ("ALERT: ArcGIS Health Check Issues Detected on gis.czu.cz\n\n"
					 "The following issues were found:\n")
	for r in website_results:
		if r["status"] != "SUCCESS":
			error_message += f"\n{r['url']} ({r['type']}) - {r['error']}"
	if arcgis_result["status"] != "SUCCESS":
		error_message += f"\nArcGIS Publishing Test: {arcgis_result['error']}"
	error_message += "\n\nPlease investigate immediately."
	print("ALERT: Failures detected. Sending alert email...")
	send_email("🚨 ALERT: ArcGIS Server Health Check Failure", error_message, attachment_path=pdf_report)
else:
	success_message = "✅ All ArcGIS services are running normally."
	print("SUCCESS: All ArcGIS services are running normally. Sending success email...")
	send_email("✅ ArcGIS Health Check Passed", success_message, attachment_path=pdf_report)
