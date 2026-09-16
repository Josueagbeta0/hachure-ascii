import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from hachure.media.video import (
    MediaSource,
    VideoOptions,
    VideoRenderError,
    _build_command,
    _grid_for,
    _stop_process,
    _stream_rotation,
    camera_source,
    get_video_dimensions,
    parse_dshow_devices,
    play_video,
    read_frame,
)
from hachure.render import RenderStyle


def _probe_result(payload: dict) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=["ffprobe"], returncode=0, stdout=json.dumps(payload), stderr=""
    )


class UtilitairesVideoTests(unittest.TestCase):
    def test_read_frame_recolle_les_lectures_partielles(self) -> None:
        self.assertEqual(read_frame(io.BytesIO(b"abcdef"), 6), b"abcdef")

    def test_read_frame_rejette_une_image_finale_incomplete(self) -> None:
        self.assertIsNone(read_frame(io.BytesIO(b"abc"), 6))

    def test_les_valeurs_video_par_defaut_sont_sures(self) -> None:
        options = VideoOptions()
        self.assertGreater(options.fps, 0)
        self.assertGreater(options.max_width, 0)
        self.assertGreaterEqual(options.max_frame_skip, 0)

    def test_le_nettoyage_tue_un_processus_qui_refuse_de_s_arreter(self) -> None:
        process = mock.Mock()
        process.poll.return_value = None
        process.wait.side_effect = subprocess.TimeoutExpired("ffmpeg", 2)

        _stop_process(process)

        process.terminate.assert_called_once_with()
        process.kill.assert_called_once_with()

    def test_l_absence_de_ffmpeg_donne_une_erreur_claire(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            video = Path(directory) / "movie.mp4"
            video.write_bytes(b"")
            with mock.patch(
                "hachure.media.video.shutil.which", return_value=None
            ):
                with self.assertRaisesRegex(VideoRenderError, "FFmpeg est introuvable"):
                    play_video(
                        video,
                        options=VideoOptions(audio=False),
                        style=RenderStyle(" .#"),
                    )


class DimensionsVideoTests(unittest.TestCase):
    @mock.patch("hachure.media.video.subprocess.run")
    @mock.patch("hachure.media.video.shutil.which", return_value="ffprobe")
    def test_les_dimensions_sont_lues_via_ffprobe(
        self, _which: mock.Mock, run: mock.Mock
    ) -> None:
        run.return_value = _probe_result({"streams": [{"width": 1920, "height": 1080}]})

        self.assertEqual(get_video_dimensions(Path("movie.mp4")), (1920, 1080))
        self.assertEqual(run.call_args.args[0][0], "ffprobe")

    @mock.patch("hachure.media.video.subprocess.run")
    @mock.patch("hachure.media.video.shutil.which", return_value="ffprobe")
    def test_une_rotation_en_side_data_echange_les_axes(
        self, _which: mock.Mock, run: mock.Mock
    ) -> None:
        run.return_value = _probe_result(
            {
                "streams": [
                    {
                        "width": 1920,
                        "height": 1080,
                        "side_data_list": [{"rotation": -90}],
                    }
                ]
            }
        )

        self.assertEqual(get_video_dimensions(Path("phone.mp4")), (1080, 1920))

    @mock.patch("hachure.media.video.subprocess.run")
    @mock.patch("hachure.media.video.shutil.which", return_value="ffprobe")
    def test_le_tag_rotate_echange_les_axes(self, _which: mock.Mock, run: mock.Mock) -> None:
        run.return_value = _probe_result(
            {"streams": [{"width": 1920, "height": 1080, "tags": {"rotate": "90"}}]}
        )

        self.assertEqual(get_video_dimensions(Path("phone.mp4")), (1080, 1920))

    def test_une_video_droite_garde_ses_axes(self) -> None:
        self.assertEqual(_stream_rotation({"tags": {"rotate": "180"}}), 180)
        self.assertEqual(_stream_rotation({}), 0)


class ConstructionDeCommandeTests(unittest.TestCase):
    def _source(self) -> MediaSource:
        return MediaSource(
            input_args=["-i", "movie.mp4"], label="movie.mp4", dimensions=(1920, 1080)
        )

    def test_les_cellules_half_demandent_deux_fois_plus_de_lignes(self) -> None:
        source = self._source()
        options = VideoOptions(max_width=80, max_height=20)
        style = RenderStyle(" .#", cell_mode="half")
        cols, rows, _ = _grid_for(source, options, style)

        command = _build_command(
            source, options, style, cols=cols, rows=rows, crop=None, position=0.0
        )
        filters = command[command.index("-vf") + 1]

        self.assertIn(f"scale={cols}:{rows * 2}", filters)

    def test_un_saut_transmet_un_decalage_d_entree(self) -> None:
        source = self._source()
        options = VideoOptions(start=12.0, duration=5.0)
        style = RenderStyle(" .#")

        command = _build_command(
            source, options, style, cols=40, rows=20, crop=None, position=12.0
        )

        self.assertIn("-ss", command)
        self.assertEqual(command[command.index("-ss") + 1], "12.000")
        self.assertIn("-t", command)

    def test_l_ajustement_cover_recadre_la_source(self) -> None:
        source = self._source()
        options = VideoOptions(fit="cover", max_width=80, max_height=20)
        style = RenderStyle(" .#")
        cols, rows, crop = _grid_for(source, options, style)

        self.assertIsNotNone(crop)
        command = _build_command(
            source, options, style, cols=cols, rows=rows, crop=crop, position=0.0
        )
        self.assertIn("crop=", command[command.index("-vf") + 1])

    def test_les_marqueurs_de_peripherique_du_ffmpeg_moderne_sont_lus(self) -> None:
        output = (
            '[in#0 @ 0x1] "Integrated Webcam" (none)\n'
            '[in#0 @ 0x1]   Alternative name "@device_pnp_\\\\?\\usb#vid"\n'
            '[in#0 @ 0x1] "Microphone Array" (audio)\n'
        )
        self.assertEqual(parse_dshow_devices(output), ["Integrated Webcam"])

    def test_l_ancienne_liste_de_peripheriques_par_sections_est_lue(self) -> None:
        output = (
            "[dshow @ 0x1] DirectShow video devices\n"
            '[dshow @ 0x1]  "HD WebCam"\n'
            '[dshow @ 0x1]     Alternative name "@device_pnp_x"\n'
            "[dshow @ 0x1] DirectShow audio devices\n"
            '[dshow @ 0x1]  "Line In"\n'
        )
        self.assertEqual(parse_dshow_devices(output), ["HD WebCam"])

    def test_une_source_camera_n_est_pas_positionnable(self) -> None:
        with mock.patch("hachure.media.video.platform.system", return_value="Linux"):
            source = camera_source("/dev/video0", size="640x480")
        self.assertFalse(source.seekable)
        self.assertFalse(source.has_audio)
        self.assertIn("-video_size", source.input_args)


if __name__ == "__main__":
    unittest.main()
