Feature: Change runtime settings
  Frostbite applies editable settings immediately and remembers their overrides.

  Scenario: Disable Playback Reheat and restore the saved choice
    Given Playback Reheat is enabled
    When it is disabled through the settings API
    Then the settings API reports Playback Reheat as disabled
    And the saved override is "False"
    And reloading saved settings keeps Playback Reheat disabled

  Scenario: Update an existing threshold override
    Given a stored override exists for the freeze threshold
    When the freeze threshold is changed to 12.5
    Then the stored override is updated to "12.5"
    And the active freeze threshold is 12.5

  Scenario: Save a newly edited setting
    Given there is no stored override for the prefetch cooldown
    When the prefetch cooldown is changed to 7 days
    Then an override for 7 days is added
    And the active prefetch cooldown is 7 days

  Scenario: Refuse changes to non-editable settings
    Given the database connection is not an editable setting
    When an override for the database connection is requested
    Then the change is rejected without opening a database session
