@qso-lookup
Feature: QSO lookup
  As a fellow radio amateur
  I want to check whether we have QSOs in the LU2MET log
  So that I can confirm a contact without asking by email

  @api @contract
  Scenario Outline: Lookup responses follow the QSO lookup contract
    When I look up the callsign "<callsign>" through the API
    Then the response status is 200
    And the response matches the QSO lookup contract

    Examples:
      | callsign | case                     |
      | LU3MRP   | station found            |
      | CA3PHX   | station not found        |
      | KE4TT    | found through a portable |

  @api
  Scenario Outline: A station from the log is found with its QSOs
    When I look up the callsign "<callsign>" through the API
    Then the response status is 200
    And the response says the station was found
    And the response contains at least one QSO

    Examples:
      | callsign |
      | LU3MRP   |
      | ES5NC    |
      | MW0JKU   |

  @api
  Scenario: A station that is not in the log is reported as not found
    When I look up the callsign "CA3PHX" through the API
    Then the response status is 200
    And the response says the station was not found
    And the response contains no QSOs

  @api
  Scenario Outline: Base and portable forms of a callsign find each other's QSOs
    When I look up the callsign "<callsign>" through the API
    Then the response says the station was found
    And the response contains a QSO logged as "<logged_as>"

    Examples:
      | callsign | logged_as | case                    |
      | LU1MAW   | LU1MAW/M  | base finds suffix form  |
      | LU1MAW/M | LU1MAW    | suffix form finds base  |
      | KE4TT    | V4/KE4TT  | base finds prefix form  |

  @api
  Scenario: Filtering by a band with QSOs returns only that band
    When I look up the callsign "LU3MRP" filtered by band "2m" through the API
    Then the response says the station was found
    And every QSO in the response is on band "2m"

  @api
  Scenario: Filtering by a band without QSOs reports the station as not found
    When I look up the callsign "LU3MRP" filtered by band "20m" through the API
    Then the response says the station was not found
    And the response contains no QSOs

  @api
  Scenario: Callsign lookup is case-insensitive
    When I look up the callsign "lu3mrp" through the API
    Then the response says the station was found
    And the response reports the callsign as "LU3MRP"

  @api
  Scenario: Surrounding whitespace in the callsign is ignored
    When I look up the callsign " LU3MRP " through the API
    Then the response says the station was found
    And the response reports the callsign as "LU3MRP"

  @api
  Scenario Outline: An invalid callsign is rejected
    When I look up the callsign "<callsign>" through the API
    Then the response status is 400
    And the response reports the error "invalid_callsign"

    Examples:
      | callsign  |
      | !!bad     |
      | 333aaazzz |

  @api
  Scenario: The log data is kept up to date
    When I check the health of the QSO lookup API
    Then the response status is 200
    And the health status is "ok"
    And the last synchronization happened less than 48 hours ago
    
  @ui
  Scenario: Looking up a station from the log shows its QSOs
    Given I am on the QSO lookup page "/log-check"
    When I enter "LU3MRP" in the "Tu indicativo" field and press the "Consultar →" button
    Then the result message contains "¡Sí!"
    And the results table has exactly the columns "Fecha", "Banda", "Modo", "LoTW" and "Logueado como"

  @ui
  Scenario: Looking up a station that is not in the log says so
    Given I am on the QSO lookup page "/log-check"
    When I enter "CA3PHX" in the "Tu indicativo" field and press the "Consultar →" button
    Then the result message contains "No hay QSOs con CA3PHX en mi log."
    And no results table is shown

  @ui
  Scenario: An invalid callsign shows a validation message
    Given I am on the QSO lookup page "/log-check"
    When I enter "!!bad" in the "Tu indicativo" field and press the "Consultar →" button
    Then the result message contains "Eso no parece un indicativo."