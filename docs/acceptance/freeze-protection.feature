Feature: Protect recently warmed media from automatic freezing
  Prefetch and manual reheat protection avoid undoing an intentional warmup.

  Scenario: A recently prefetched hot item has a grace period
    Given a hot item was prefetched 4 hours ago
    And the prefetch grace period is 12 hours
    And it has not been watched since the prefetch
    When Frostbite evaluates an automatic freeze
    Then the item remains protected until 12 hours after the prefetch
    And the queued automatic freeze has a protection reason

  Scenario Outline: Prefetch protection stops when it no longer applies
    Given a hot item was prefetched with a 12 hour grace period
    When <condition>
    Then the item has no prefetch protection

    Examples:
      | condition                                     |
      | it is watched after the prefetch              |
      | more than 12 hours have passed since prefetch |

  Scenario: A playback-history lookup failure keeps the time-based grace period
    Given a hot item was prefetched one hour ago
    And playback history cannot be read
    When Frostbite checks prefetch protection
    Then the item remains protected until its 12 hour grace period ends

  Scenario: Manual freeze can override prefetch protection
    Given a hot item is protected after a prefetch
    When a manual freeze is evaluated
    Then the prefetch protection does not cancel the manual freeze

  Scenario: Manual reheat protects against automatic and space-pressure freezes
    Given a hot item was manually reheated one day ago
    And the manual reheat protection window is 2 days
    When queued freezes are evaluated
    Then automatic and space-pressure freezes are canceled
    But a manual freeze can remain queued

  Scenario: A playback reheat is kept only while the item is cold
    Given a playback-triggered reheat is queued for a cold item with a low score
    When the queued transfer is evaluated
    Then the low score does not cancel the reheat
    But it is canceled if the item is no longer cold

  Scenario: A transfer response includes protection details
    Given an item has active prefetch and manual reheat protection
    When its transfer response is prepared
    Then both protection flags and their expiry times are included
