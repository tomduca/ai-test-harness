@navigation @smoke
Feature: Main navigation
  As a visitor of lu2met.ar
  I want the main menu to take me to each part of the site
  So that I can quickly find projects, on-air activity, 
  the QSO lookup, the workshop and the directory

  Background:
    Given I am on the home page

  Scenario Outline: Each menu item takes the visitor to its content
    When I select the "<item>" menu item
    Then I see content titled "<expected_title>"

    Examples:
      | item       | expected_title        |
      | Proyectos  | Del banco de trabajo  |
      | En el aire | En el aire            |
      | QSOs       | Consulta nuestros QSOs |
      | Taller     | El taller             |
      | Directorio | Directorio            |

  Scenario: The home page loads cleanly
    Then the page shows no JavaScript errors in the console
    And every image on the page loads successfully

  Scenario: The main menu offers exactly the expected items
    Then the main menu contains exactly these items, in this order:
    | Proyectos  |
    | En el aire |
    | QSOs       |
    | Taller     |
    | Directorio |

  Scenario: Switching the site language to English
    When I select the "EN" language link
    Then the URL path is "/en/"
    And the main menu contains exactly these items, in this order:
      | Projects   |
      | On the air |
      | QSOs       |
      | Workshop   |
      | Directory  |