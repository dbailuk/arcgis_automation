import os
import logging
from arcgis.gis import GIS
import matplotlib.pyplot as plt
from datetime import datetime, timedelta, timezone
import csv
from collections import Counter
import smtplib
from email.message import EmailMessage
import io
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

# Ensure the folder for logs and reports exists before configuring logging
reports_folder = "logs_reports"
if not os.path.exists(reports_folder):
	os.makedirs(reports_folder)

log_file_path = os.path.join(reports_folder, "user_management_log.txt")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
# Create and add a file handler for logging
file_handler = logging.FileHandler(log_file_path)
file_handler.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
file_handler.setFormatter(formatter)
logging.getLogger().addHandler(file_handler)
logging.info("Starting ArcGIS User Management Report Generation")

# Configuration settings: SMTP details and inactivity threshold (in days)
CONFIG = {
	"smtp": {
		"server": "smtp.gmail.com",
		"port": 587,
		"username": "",
		"password": "",
		"recipient": ""
	},
	"inactive_threshold": 70
}

def send_email(subject, message, attachment_path=None):
	"""Send an email with an optional PDF attachment."""
	try:
		msg = EmailMessage()
		msg.set_content(message)
		msg["Subject"] = subject
		msg["From"] = CONFIG["smtp"]["username"]
		msg["To"] = CONFIG["smtp"]["recipient"]

		# Attach the PDF if provided and exists
		if attachment_path and os.path.exists(attachment_path):
			with open(attachment_path, 'rb') as f:
				file_data = f.read()
			msg.add_attachment(file_data, maintype="application", subtype="pdf",
				filename=os.path.basename(attachment_path))
			logging.info(f"Attached PDF report: {attachment_path}")

		with smtplib.SMTP(CONFIG["smtp"]["server"], CONFIG["smtp"]["port"]) as server:
			logging.info("Connecting to SMTP server")
			server.starttls()
			server.login(CONFIG["smtp"]["username"], CONFIG["smtp"]["password"])
			server.send_message(msg)
			logging.info("Email alert sent successfully.")
	except Exception as e:
		logging.error(f"Failed to send email: {e}")

def generate_pdf_report(pdf_path, summary_message, csv_file_path, pie_buffer, bar_buffer, role_buffer):
	"""Generate a PDF report with a header, summary text, and embedded charts."""
	try:
		c = canvas.Canvas(pdf_path, pagesize=letter)
		width, height = letter
		y_position = height - 50

		# Draw the centered header
		c.setFont("Helvetica-Bold", 18)
		header_text = "ArcGIS User Management Report"
		c.drawCentredString(width / 2, y_position, header_text)
		y_position -= 30

		# Draw the summary text
		c.setFont("Helvetica", 10)
		logging.info("Adding summary text to PDF report")
		for line in summary_message.splitlines():
			c.drawString(50, y_position, line)
			y_position -= 12
			if y_position < 100:
				c.showPage()
				y_position = height - 50
				c.setFont("Helvetica", 10)
		y_position -= 20

		# Embed the Pie Chart (Active vs. Inactive Users)
		if pie_buffer:
			logging.info("Embedding Pie Chart in PDF")
			pie_image = ImageReader(pie_buffer)
			img_width, img_height = pie_image.getSize()
			aspect = img_height / float(img_width)
			display_width = 400
			display_height = display_width * aspect
			x_position = (width - display_width) / 2
			if y_position - display_height < 50:
				c.showPage()
				y_position = height - 50
			c.drawImage(pie_image, x_position, y_position - display_height, width=display_width, height=display_height)
			y_position -= display_height + 20

		# Embed the Bar Chart (Suggested Actions Distribution)
		if bar_buffer:
			logging.info("Embedding Bar Chart in PDF")
			bar_image = ImageReader(bar_buffer)
			img_width, img_height = bar_image.getSize()
			aspect = img_height / float(img_width)
			display_width = 400
			display_height = display_width * aspect
			x_position = (width - display_width) / 2
			if y_position - display_height < 50:
				c.showPage()
				y_position = height - 50
			c.drawImage(bar_image, x_position, y_position - display_height, width=display_width, height=display_height)
			y_position -= display_height + 20

		# Embed the Extra Chart (User Role Distribution)
		if role_buffer:
			logging.info("Embedding User Role Distribution Chart in PDF")
			role_image = ImageReader(role_buffer)
			img_width, img_height = role_image.getSize()
			aspect = img_height / float(img_width)
			display_width = 400
			display_height = display_width * aspect
			x_position = (width - display_width) / 2
			if y_position - display_height < 50:
				c.showPage()
				y_position = height - 50
			c.drawImage(role_image, x_position, y_position - display_height, width=display_width, height=display_height)
			y_position -= display_height + 20

		c.showPage()
		c.save()
		logging.info(f"PDF report generated at '{pdf_path}'")
	except Exception as e:
		logging.error(f"Error generating PDF report: {e}")

# Set CET timezone (Central European Time)
tz_cet = timezone(timedelta(hours=1))
logging.info("Timezone set to CET")

# Authenticate to the ArcGIS Portal using a saved token
saved_token = "Q"
try:
	gis = GIS("https://gis.czu.cz/portal", token=saved_token)
	logging.info("Connected to ArcGIS Portal")
except Exception as e:
	logging.error(f"Failed to connect to ArcGIS Portal: {e}")
	exit()

# Set the inactivity threshold (in days)
inactive_threshold = CONFIG.get("inactive_threshold", 70)
logging.info(f"Inactivity threshold set to {inactive_threshold} days.")

# Retrieve all users from the GIS portal
logging.info("Retrieving all users from the portal")
all_users = gis.users.search(max_users=1000)
logging.info(f"Retrieved {len(all_users)} users from the portal")

now = datetime.now(timezone.utc)
logging.info("Current UTC time obtained")

user_data = []
inactive_users = []
role_counts = Counter()
suggested_actions_counter = Counter()

# Process each user and collect relevant data
logging.info("Processing user data")
for user in all_users:
	logging.info(f"Processing user: {user.username}")
	# Determine the last login and inactivity period
	if user.lastLogin == -1:
		last_login = "Never Logged In"
		days_inactive = None
		logging.debug(f"User {user.username} has never logged in.")
	else:
		last_login_dt = datetime.fromtimestamp(user.lastLogin / 1000, tz=timezone.utc)
		last_login = last_login_dt.strftime("%Y-%m-%d")
		days_inactive = (now - last_login_dt).days
		logging.debug(f"User {user.username} last logged in on {last_login} ({days_inactive} days ago)")

	role = user.role
	role_counts[role] += 1

	# Retrieve group information
	try:
		groups = ", ".join([group.title for group in user.groups]) if user.groups else "No Groups"
		logging.debug(f"User {user.username} groups: {groups}")
	except Exception as ex:
		groups = "No Groups"
		logging.error(f"Error retrieving groups for user {user.username}: {ex}")

	# Get the number of content items for the user
	try:
		items = user.items()
		content_count = len(items)
		logging.debug(f"User {user.username} has {content_count} content items")
	except Exception as e:
		logging.error(f"Error retrieving items for user {user.username}: {e}")
		content_count = 0

	# Determine the suggested action based on inactivity and content count
	suggested_action = "Do nothing"
	if last_login == "Never Logged In" or (days_inactive is not None and days_inactive > inactive_threshold):
		if content_count > 0:
			if content_count > 5:
				suggested_action = "Archive content and delete user"
			else:
				suggested_action = "Delete both content and user"
		else:
			suggested_action = "Delete user"
	logging.info(f"Suggested action for user {user.username}: {suggested_action}")
	suggested_actions_counter[suggested_action] += 1

	user_data.append([
		user.username, user.fullName, user.email, role, groups,
		last_login, days_inactive, content_count, suggested_action
	])
	if days_inactive and days_inactive > inactive_threshold:
		inactive_users.append([user.username, last_login, days_inactive])

logging.info(f"Found {len(all_users)} users. {len(inactive_users)} inactive for more than {inactive_threshold} days.")

# Save user details and decision support data to a CSV file
csv_file_path = os.path.join(reports_folder, "inactive_users_report.csv")
try:
	with open(csv_file_path, "w", newline="", encoding="utf-8-sig") as file:
		writer = csv.writer(file)
		writer.writerow([
			"Username", "Full Name", "Email", "Role", "Groups",
			"Last Login", "Days Inactive", "Content Count", "Suggested Action"
		])
		writer.writerows(user_data)
	logging.info(f"User details report saved as '{csv_file_path}'")
except Exception as e:
	logging.error(f"Error saving CSV report: {e}")

# Calculate key statistics for the summary
total_users = len(all_users)
total_content = sum([row[7] for row in user_data])
average_content = total_content / total_users if total_users > 0 else 0
inactive_days_list = [row[6] for row in user_data if row[6] is not None]
average_inactive_days = sum(inactive_days_list) / len(inactive_days_list) if inactive_days_list else 0

stats_summary = (
	f"Total Users: {total_users}\n"
	f"Average Content Count per User: {average_content:.2f}\n"
	f"Average Inactive Days (for users with data): {average_inactive_days:.2f}\n"
	f"Inactive Users (> {inactive_threshold} days): {len(inactive_users)}\n"
)

# Build the summary message including statistics and suggested actions distribution
summary_message = (
	"Summary\n\n" +
	stats_summary +
	"\nSuggested Actions Distribution:\n"
)
for action, count in suggested_actions_counter.items():
	summary_message += f" - {action}: {count}\n"
summary_message += f"\nDetailed CSV Report: {csv_file_path}"

logging.info("Summary message built for PDF report")

# Generate charts in memory

# Pie Chart: Active vs. Inactive Users
active_count = max(0, len(all_users) - len(inactive_users))
inactive_count = max(0, len(inactive_users))
if active_count + inactive_count > 0:
	pie_buffer = io.BytesIO()
	logging.info("Generating Pie Chart for Active vs. Inactive Users")
	plt.figure(figsize=(6, 6))
	plt.pie([active_count, inactive_count], labels=["Active Users", "Inactive Users"],
		autopct='%1.1f%%')
	plt.title("Active vs. Inactive Users")
	plt.savefig(pie_buffer, format="png")
	plt.close()
	pie_buffer.seek(0)
else:
	pie_buffer = None
	logging.warning("No data available for Pie Chart generation")

# Bar Chart: Suggested Actions Distribution
if suggested_actions_counter:
	bar_buffer = io.BytesIO()
	logging.info("Generating Bar Chart for Suggested Actions Distribution")
	plt.figure(figsize=(8, 6))
	actions = list(suggested_actions_counter.keys())
	counts = list(suggested_actions_counter.values())
	plt.bar(actions, counts)
	plt.xlabel("Suggested Action")
	plt.ylabel("Number of Users")
	plt.title("Suggested Actions Distribution")
	plt.xticks(rotation=45, ha='right')
	plt.tight_layout()
	plt.savefig(bar_buffer, format="png")
	plt.close()
	bar_buffer.seek(0)
else:
	bar_buffer = None
	logging.warning("No data available for Bar Chart generation")

# Chart: User Role Distribution
if role_counts:
	role_buffer = io.BytesIO()
	logging.info("Generating Bar Chart for User Role Distribution")
	plt.figure(figsize=(8, 6))
	roles = list(role_counts.keys())
	counts = list(role_counts.values())
	plt.bar(roles, counts)
	plt.xlabel("User Role")
	plt.ylabel("Number of Users")
	plt.title("User Role Distribution")
	plt.xticks(rotation=45, ha='right')
	plt.tight_layout()
	plt.savefig(role_buffer, format="png")
	plt.close()
	role_buffer.seek(0)
else:
	role_buffer = None
	logging.warning("No data available for User Role Distribution Chart generation")

# Generate the PDF report with the summary and charts
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
pdf_file_path = os.path.join(reports_folder, f"inactive_users_report_{timestamp}.pdf")
logging.info("Generating PDF report")
generate_pdf_report(pdf_file_path, summary_message, csv_file_path, pie_buffer, bar_buffer, role_buffer)

logging.info("User Management Automation Completed!")

# Send a summary email with the PDF report attached
email_subject = "ArcGIS User Management Report Summary"
summary_message_email = summary_message + "\n\nPDF report attached."
logging.info("Sending summary email with PDF attachment")
send_email(email_subject, summary_message_email, attachment_path=pdf_file_path)
