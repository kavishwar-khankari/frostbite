Feature: Start and execute safe media transfers
  Frostbite blocks unsafe or premature transfers before moving a media file.

  Scenario Outline: NAS usage is measured in GiB for the cold transfer gate
    Given freezing requires at least 3000 GiB of NAS usage
    When NAS usage is <used_gib> GiB
    Then new freeze transfers are <decision>

    Examples:
      | used_gib | decision |
      | 2999.5   | paused   |
      | 3000     | allowed  |

  Scenario: An unknown NAS usage keeps the cold transfer gate closed
    Given freezing requires a positive NAS usage threshold
    When NAS usage cannot be read
    Then new freeze transfers are paused with an explanation

  Scenario: A zero NAS usage threshold disables the gate
    Given the cold transfer NAS usage limit is zero
    When NAS usage cannot be read
    Then the NAS usage gate permits new freeze transfers

  Scenario Outline: Queued freezes report their first start blocker
    Given at least one freeze is queued
    When <condition>
    Then the freeze start blocker is <blocker>

    Examples:
      | condition                                  | blocker            |
      | the transfer worker is paused             | global_pause       |
      | the freeze concurrency limit is reached   | freeze_concurrency |
      | the configured freeze window is inactive  | freeze_window      |
      | the NAS usage gate does not permit a start | nas_usage_gate     |

  Scenario: Reheats respect pause and concurrency limits
    Given a reheat is queued
    When the transfer worker is paused or the reheat concurrency limit is reached
    Then Frostbite reports the corresponding reheat start blocker

  Scenario Outline: Unsafe transfer filenames fail preflight
    Given a queued media transfer has <problem>
    When Frostbite checks the transfer before copying
    Then the transfer is marked failed with <reason>

    Examples:
      | problem                               | reason                       |
      | a .nfo source file                    | a disallowed media extension |
      | a freeze filename over 120 characters | a filename-too-long error    |

  Scenario: Legacy absolute paths are normalized before checking the NAS
    Given a queued transfer stores a path under the old Jellyfin media root
    When Frostbite checks whether its source exists on the NAS
    Then the transfer uses a relative media path
    And the missing-source error points to the NAS path

  Scenario: VFS cache invalidation includes the file and its parent folders
    Given a changed or deleted media file is nested under a show and season
    When Frostbite requests VFS cache invalidation
    Then the request forgets the file, its season folder, and its show folder
