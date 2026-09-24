Feature: Understand Jellyfin playback notifications
  Playback events are normalized before Frostbite uses them to manage media.

  Scenario: Accept a flat webhook with a zero playback position
    Given a flat Jellyfin PlaybackStart notification has a hyphenated item ID
    And its playback position is the string "0"
    When Frostbite parses the notification
    Then the item ID has no hyphens
    And the event type is "start"
    And the playback position is zero rather than missing

  Scenario: Accept the newer playback position field
    Given a Jellyfin PlaybackStart notification contains PlaybackPositionTicks equal to zero
    When Frostbite parses the notification
    Then the playback position is zero rather than missing

  Scenario: Fall back to stock nested webhook fields
    Given a Jellyfin notification contains nested Item and Session details
    When Frostbite parses the notification
    Then the item, user, play method, and playback position come from the nested details
    And an unrecognized notification type is recorded as "unknown"

  Scenario: Treat an absent playback position as unknown
    Given a notification has no playback position
    When Frostbite parses the notification
    Then its playback position is missing rather than zero
