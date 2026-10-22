// Where the camera is "looking" on the ground — used to fit the shadow camera.
import { Vector3 } from "three";

const focus = new Vector3();

export function setCameraFocus(x: number, y: number, z: number) {
  focus.set(x, y, z);
}

export function cameraFocus(): Vector3 {
  return focus;
}
