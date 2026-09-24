Feature: Reheat cold media after new playback
  A resumed play counts only watching since the current session began.

  Scenario Outline: A cold item becomes eligible at the configured threshold
    Given Playback Reheat is enabled with a threshold of 60 seconds
    And an item is stored in the cold tier
    When Frostbite evaluates <seconds> seconds of new playback
    Then the item is <eligibility> for playback reheat

    Examples:
      | seconds | eligibility  |
      | 59      | not eligible |
      | 60      | eligible     |

  Scenario Outline: Resuming from a bookmark does not skip the reheat clock
    Given a cold item resumes at 45 minutes into its runtime
    And the playback reheat threshold is 60 seconds
    When the playback position reaches <position>
    Then <new_seconds> seconds of new playback have elapsed
    And the item is <eligibility> for playback reheat

    Examples:
      | position | new_seconds | eligibility  |
      | 45:30    | 30          | not eligible |
      | 46:00    | 60          | eligible     |

  Scenario Outline: A non-cold item is not eligible for playback reheat
    Given an item is in the <tier> tier
    And Playback Reheat is enabled
    When Frostbite evaluates 10 minutes of new playback
    Then the item is not eligible for playback reheat

    Examples:
      | tier         |
      | hot          |
      | transferring |

  Scenario: A disabled setting prevents playback reheat
    Given Playback Reheat is disabled
    And an item is stored in the cold tier
    When Frostbite evaluates 10 minutes of new playback
    Then the item is not eligible for playback reheat

  Scenario: Unknown playback duration does not trigger a reheat
    Given an item is stored in the cold tier
    When the session start or current playback position is unknown
    Then the new playback duration cannot be established
    And the item is not eligible for playback reheat
