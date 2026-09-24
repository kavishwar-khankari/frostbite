Feature: Calculate media temperature
  Frostbite scores media using playback, metadata, and file size signals.

  Scenario: Hot signals have an explainable breakdown and a maximum score
    Given an item was added 2 days ago and last played 14 days ago
    And it has 50 plays, 20 unique viewers, and a community rating of 8
    And it is an 8 GiB item in a continuing series
    When its temperature is calculated
    Then the score is capped at 100
    And the breakdown includes 15 recency points and 30 newness points
    And the breakdown includes a 1.5 point size penalty

  Scenario: An old unwatched large item cannot score below zero
    Given an item was added 90 days ago and has never been played
    And it is a 20 GiB item in an ended series
    When its temperature is calculated
    Then the score is zero rather than negative
    And the breakdown includes a 5 point size penalty

  Scenario: Playback recency uses the same instant across time zones
    Given an item's last play was recorded in a timezone-aware IST timestamp
    When its temperature is calculated using UTC time
    Then the recency score reflects the equivalent UTC instant
