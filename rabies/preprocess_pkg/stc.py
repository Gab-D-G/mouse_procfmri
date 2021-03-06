from nipype.pipeline import engine as pe
from nipype.interfaces.utility import Function
from nipype.interfaces import utility as niu


def init_bold_stc_wf(tr, tpattern, no_STC=False, rabies_data_type=8, rabies_mem_scale=1.0, min_proc=1, name='bold_stc_wf'):
    """
    This workflow performs :abbr:`STC (slice-timing correction)` over the input
    :abbr:`BOLD (blood-oxygen-level dependent)` image.

    **Parameters**

        name : str
            Name of workflow (default: ``bold_stc_wf``)

    **Inputs**

        bold_file
            BOLD series NIfTI file
        skip_vols
            Number of non-steady-state volumes detected at beginning of ``bold_file``

    **Outputs**

        stc_file
            Slice-timing corrected BOLD series NIfTI file

    """
    import os
    workflow = pe.Workflow(name=name)
    inputnode = pe.Node(niu.IdentityInterface(
        fields=['bold_file']), name='inputnode')
    outputnode = pe.Node(niu.IdentityInterface(
        fields=['stc_file']), name='outputnode')

    if not no_STC:
        slice_timing_correction_node = pe.Node(Function(input_names=['in_file', 'tr', 'tpattern', 'rabies_data_type'],
                                                        output_names=[
                                                            'out_file'],
                                                        function=slice_timing_correction),
                                               name='slice_timing_correction', mem_gb=1.5*rabies_mem_scale)
        slice_timing_correction_node.inputs.rabies_data_type = rabies_data_type
        slice_timing_correction_node.plugin_args = {
            'qsub_args': '-pe smp %s' % (str(3*min_proc)), 'overwrite': True}

        workflow.connect([
            (inputnode, slice_timing_correction_node, [('bold_file', 'in_file')]),
            (slice_timing_correction_node,
             outputnode, [('out_file', 'stc_file')]),
        ])
    else:
        workflow.connect([
            (inputnode, outputnode, [('bold_file', 'stc_file')]),
        ])

    return workflow


def slice_timing_correction(in_file, tr='1.0s', tpattern='alt', rabies_data_type=8):
    '''
    This functions applies slice-timing correction on the anterior-posterior
    slice acquisition direction. The input image, assumed to be in RAS orientation
    (accoring to nibabel; note that the nibabel reading of RAS corresponds to
     LPI for AFNI). The A and S dimensions will be swapped to apply AFNI's
    3dTshift STC with a quintic fitting function, which can only be applied to
    the Z dimension of the data matrix. The corrected image is then re-created with
    proper axes and the corrected timeseries.

    **Inputs**

        in_file
            BOLD series NIfTI file in RAS orientation.
        ignore
            Number of non-steady-state volumes detected at beginning of ``bold_file``
        tr
            TR of the BOLD image.
        tpattern
            Input to AFNI's 3dTshift -tpattern option, which specifies the
            directionality of slice acquisition, or whether it is sequential or
            interleaved.

    **Outputs**

        out_file
            Slice-timing corrected BOLD series NIfTI file

    '''

    import os
    import SimpleITK as sitk
    import numpy as np

    if tpattern == "alt":
        tpattern = 'alt-z'
    elif tpattern == "seq":
        tpattern = 'seq-z'
    else:
        raise ValueError('Invalid --tpattern provided.')

    img = sitk.ReadImage(in_file, rabies_data_type)

    # get image data
    img_array = sitk.GetArrayFromImage(img)

    shape = img_array.shape
    new_array = np.zeros([shape[0], shape[2], shape[1], shape[3]])
    for i in range(shape[2]):
        new_array[:, i, :, :] = img_array[:, :, i, :]

    image_out = sitk.GetImageFromArray(new_array, isVector=False)
    sitk.WriteImage(image_out, 'STC_temp.nii.gz')

    command = '3dTshift -quintic -prefix temp_tshift.nii.gz -tpattern %s -TR %s STC_temp.nii.gz' % (
        tpattern, tr,)
    from rabies.preprocess_pkg.utils import run_command
    rc = run_command(command)

    tshift_img = sitk.ReadImage(
        'temp_tshift.nii.gz', rabies_data_type)
    tshift_array = sitk.GetArrayFromImage(tshift_img)

    new_array = np.zeros(shape)
    for i in range(shape[2]):
        new_array[:, :, i, :] = tshift_array[:, i, :, :]
    image_out = sitk.GetImageFromArray(new_array, isVector=False)

    from rabies.preprocess_pkg.utils import copyInfo_4DImage
    image_out = copyInfo_4DImage(image_out, img, img)

    import pathlib  # Better path manipulation
    filename_split = pathlib.Path(in_file).name.rsplit(".nii")
    out_file = os.path.abspath(filename_split[0]+'_tshift.nii.gz')
    sitk.WriteImage(image_out, out_file)
    return out_file
