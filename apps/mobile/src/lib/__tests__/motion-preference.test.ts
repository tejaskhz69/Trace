/**
 * Reduce Motion.
 *
 * The scanner's reticle is the one looping animation in the product a user
 * cannot look away from: it runs over a live camera feed for the length of a
 * lookup while they point the phone at something. That is the combination
 * that provokes vestibular symptoms, so honouring the OS setting matters more
 * here than anywhere else in the app — and nothing in the app consulted
 * `AccessibilityInfo` before this.
 */

import { renderHook, act } from '@testing-library/react-native';
import { AccessibilityInfo } from 'react-native';

import { useReducedMotion } from '../motion-preference';

describe('useReducedMotion', () => {
  let listeners: Array<(v: boolean) => void>;
  let remove: jest.Mock;

  beforeEach(() => {
    listeners = [];
    remove = jest.fn();
    // Cast through `never`: AccessibilityInfo.addEventListener is an
    // overloaded signature keyed on the event name, and TypeScript resolves
    // the spy against the FIRST overload ('announcementFinished') rather than
    // the reduceMotionChanged one we are mocking.
    jest.spyOn(AccessibilityInfo, 'addEventListener').mockImplementation(((
      event: string,
      cb: (v: boolean) => void,
    ) => {
      if (event === 'reduceMotionChanged') listeners.push(cb);
      return { remove };
    }) as never);
  });

  afterEach(() => jest.restoreAllMocks());

  it('defaults to normal motion before the OS answers', () => {
    jest
      .spyOn(AccessibilityInfo, 'isReduceMotionEnabled')
      .mockReturnValue(new Promise(() => {}) as never);
    const { result } = renderHook(() => useReducedMotion());
    expect(result.current).toBe(false);
  });

  it('reports the setting once the OS answers', async () => {
    jest
      .spyOn(AccessibilityInfo, 'isReduceMotionEnabled')
      .mockResolvedValue(true as never);
    const { result } = renderHook(() => useReducedMotion());
    await act(async () => {
      await Promise.resolve();
    });
    expect(result.current).toBe(true);
  });

  it('reports normal motion when the setting is off', async () => {
    jest
      .spyOn(AccessibilityInfo, 'isReduceMotionEnabled')
      .mockResolvedValue(false as never);
    const { result } = renderHook(() => useReducedMotion());
    await act(async () => {
      await Promise.resolve();
    });
    expect(result.current).toBe(false);
  });

  it('follows a change made without leaving the app', async () => {
    // Control Centre can flip this mid-session. A value captured at mount
    // would be stale for the rest of the run.
    jest
      .spyOn(AccessibilityInfo, 'isReduceMotionEnabled')
      .mockResolvedValue(false as never);
    const { result } = renderHook(() => useReducedMotion());
    await act(async () => {
      await Promise.resolve();
    });
    expect(result.current).toBe(false);

    await act(async () => {
      listeners.forEach((cb) => cb(true));
    });
    expect(result.current).toBe(true);
  });

  it('does not crash when the platform cannot answer', async () => {
    // A camera screen must not fail because an accessibility query rejected.
    jest
      .spyOn(AccessibilityInfo, 'isReduceMotionEnabled')
      .mockRejectedValue(new Error('unsupported') as never);
    const { result } = renderHook(() => useReducedMotion());
    await act(async () => {
      await Promise.resolve();
    });
    expect(result.current).toBe(false);
  });

  it('unsubscribes on unmount', async () => {
    jest
      .spyOn(AccessibilityInfo, 'isReduceMotionEnabled')
      .mockResolvedValue(false as never);
    const { unmount } = renderHook(() => useReducedMotion());
    await act(async () => {
      await Promise.resolve();
    });
    unmount();
    expect(remove).toHaveBeenCalled();
  });

  it('ignores a late answer after unmount', async () => {
    // The promise resolving into a dead component is a warning at best and a
    // leak at worst.
    let resolve!: (v: boolean) => void;
    jest
      .spyOn(AccessibilityInfo, 'isReduceMotionEnabled')
      .mockReturnValue(new Promise<boolean>((r) => (resolve = r)) as never);
    const { unmount } = renderHook(() => useReducedMotion());
    unmount();
    await act(async () => {
      resolve(true);
      await Promise.resolve();
    });
    // No assertion on state — the point is that this does not throw or warn.
  });
});
