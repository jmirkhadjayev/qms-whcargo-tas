/** Opens the 80 mm ticket page in a small window and prints it right away. */
export function openTicketWindow(requestId: number): void {
  window.open(`/print/ticket/${requestId}?auto=1`, "_blank", "width=420,height=720");
}
