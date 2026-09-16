import pytest

from daou_approval.folders import resolve_folders


def test_department_folders_are_expanded_per_department():
    folders = resolve_folders(["9000021773"], ["viewer", "dept-reference"])

    paths = [folder.path for folder in folders]
    assert paths == ["doclist/viewer/all", "deptfolder/reference/9000021773"]


def test_every_folder_is_returned_when_no_keys_are_given():
    folders = resolve_folders(["1", "2"])

    assert len(folders) == 6 + (4 * 2)


def test_reception_and_official_boxes_reject_the_duration_parameter():
    folders = {folder.key: folder for folder in resolve_folders(["1"])}

    assert folders["reception"].supports_duration is False
    assert folders["dept-official"].supports_duration is False
    assert folders["viewer"].supports_duration is True


def test_unknown_folder_key_is_rejected():
    with pytest.raises(ValueError, match="nope"):
        resolve_folders(["1"], ["viewer", "nope"])
