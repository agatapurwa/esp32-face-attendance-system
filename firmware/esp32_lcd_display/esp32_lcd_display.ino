#include <WiFi.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h>

#define I2C_SDA 19
#define I2C_SCL 23

// WiFi Credentials (Placeholder)
const char* ssid = "YOUR_WIFI_SSID";
const char* password = "YOUR_WIFI_PASSWORD";

WiFiServer server(12345);
LiquidCrystal_I2C lcd(0x27, 16, 2);

void displayReady() {
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("ATTENDANCE READY");
  lcd.setCursor(0, 1);
  lcd.print("Please wait...");
}

void setup() {
  Serial.begin(115200);
  Wire.begin(I2C_SDA, I2C_SCL);

  lcd.init();
  lcd.backlight();

  lcd.print("WiFi Connecting");
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  lcd.clear();
  lcd.print("IP Address:");
  lcd.setCursor(0, 1);
  lcd.print(WiFi.localIP());
  delay(3000);

  server.begin();
  displayReady();
}

void loop() {
  WiFiClient client = server.available();

  if (client) {
    String received = client.readStringUntil('\n');
    received.trim();

    if (received.length() > 0) {
      int separatorIndex = received.indexOf('|');
      String studentName = "";
      String studentID = "";

      if (separatorIndex != -1) {
        studentName = received.substring(0, separatorIndex);
        studentID = received.substring(separatorIndex + 1);
      } else {
        studentName = received;
      }

      // 1. Display SUCCESS status
      lcd.clear();
      lcd.setCursor(0, 0);
      lcd.print("ATTENDANCE");
      lcd.setCursor(0, 1);
      lcd.print("SUCCESSFUL!");
      delay(2000);

      // 2. Display Student Name and ID
      lcd.clear();
      lcd.setCursor(0, 0);
      lcd.print(studentName);
      lcd.setCursor(0, 1);
      lcd.print(studentID);
      delay(4000);

      // 3. Queue Buffer Delay
      lcd.clear();
      lcd.setCursor(0, 0);
      lcd.print("Please Wait...");
      lcd.setCursor(0, 1);
      lcd.print("Next Queue");

      for (int i = 10; i > 0; i--) {
        lcd.setCursor(13, 1);
        lcd.print(i);
        lcd.print(" ");
        delay(1000);
      }

      displayReady();
    }
    client.stop();
  }
}