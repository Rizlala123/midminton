export interface Point {
  id: string; time: number; winner: "A" | "B" | null;
  disposition: "point_awarded" | "point_pending" | "replay/no_point";
  origin?: string; locked?: boolean; evidence?: string;
  suggested_winner?: string; contaminated?: boolean;
}
export interface Score {
  score: number[]; trusted_score: number[]; game: number; server: string;
  serving_player: string | null; provisional: boolean; pending: string[];
  conflicts: string[]; game_over: boolean;
}
export interface Anchor { id: string; team: string; box: number[]; time?: number }
export interface Document {
  id: string; revision: number; discipline: string;
  media: {path: string; duration: number; width: number; height: number};
  rules: {target: number; margin: number; cap: number; initial: number[];
          server: string; initial_server: string; initial_receiver: string};
  events: Point[]; checkpoints: {id: string; time: number; score: number[]; server: string; game: number}[];
  calibration: number[][]; anchors: Anchor[]; reanchors?: Anchor[]; models: Record<string, string>;
  analysis_options: {gpu: boolean; auto_accept?: boolean};
}
export interface ProjectView {
  document: Document; project: string; video: string; export?: string;
  timeline: {time: number; path: string; state: Score}[];
  contacts: {time: number; hitter: string | null; contaminated: boolean}[];
}
