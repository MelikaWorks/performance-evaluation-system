(function($){

    console.log("employeeprofile_ajax.js LOADED ✓");

    // --- تبدیل اعداد فارسی/عربی به انگلیسی ---
    function normalize(val){
        if(!val) return "";
        return String(val).trim()
            .replace(/[۰-۹]/g, d => "0123456789"["۰۱۲۳۴۵۶۷۸۹".indexOf(d)])
            .replace(/[٠-٩]/g, d => "0123456789"["٠١٢٣٤٥٦٧٨٩".indexOf(d)]);
    }

    function fillSelect($sel, items, placeholder, selected){
        if(!$sel.length) return;

        selected = normalize(selected);
        var oldVal = normalize($sel.val());

        $sel.empty();

        if(placeholder){
            $sel.append($('<option>', {value:"", text:placeholder}));
        }

        items.forEach(function(it){
            $sel.append($('<option>', {
                value: String(it.id),
                text: it.name
            }));
        });

        if(selected && $sel.find('option[value="'+selected+'"]').length){
            $sel.val(selected);
            return;
        }

        if(oldVal && $sel.find('option[value="'+oldVal+'"]').length){
            $sel.val(oldVal);
            return;
        }

        var opts = $sel.find('option');
        if(opts.length > 1){
            $sel.val(opts.eq(1).val());
        }
    }

    function fetchJSON(url){
        return $.ajax({
            url: url,
            method: "GET",
            xhrFields: { withCredentials:true }
        });
    }

    function init(){

        var $org   = $("#id_organization");
        var $unit  = $("#id_unit");
        var $role  = $("#id_job_role");
        var $title = $("#id_title");
        var $dir   = $("#id_direct_supervisor");
        var $chief = $("#id_section_head");
        var $mgr   = $("#id_unit_manager");

        var pathParts = window.location.pathname.split("/").filter(Boolean);
        var empID = null;

        if(pathParts.length >= 5 && pathParts[pathParts.length - 1] === "change"){
            empID = pathParts[pathParts.length - 2];
        }

        empID = normalize(empID);

        var initDir   = normalize($dir.val());
        var initChief = normalize($chief.val());
        var initMgr   = normalize($mgr.val());
        var initRole  = normalize($role.val());
        var initTitle = normalize($title.val());

        var firstLoad = true;

        // ---------------------------------------------------
        // 🔵 لود واحدهای سازمان
        // ---------------------------------------------------
        function reloadUnits(){

            var orgVal = normalize($org.val());

            if(!orgVal){
                fillSelect($unit, [], "— انتخاب کنید —", null);

                firstLoad = false;
                reloadDropdowns();
                return;
            }

            var urlUnits = window.location.origin +
                "/admin/reports/get_units_by_org/?org_id=" + orgVal;

            console.log("API Units =", urlUnits);

            fetchJSON(urlUnits).done(function(resp){

                var units = resp.units || [];

                fillSelect($unit, units, "— انتخاب کنید —", null);

                firstLoad = false;

                reloadDropdowns();
            });
        }

        // ---------------------------------------------------
        // 🔵 لود job role / title / مدیر / رئیس بر اساس واحد
        // ---------------------------------------------------
        function reloadDropdowns(){

            var unitVal = normalize($unit.val());
            console.log("Reload based on unit =", unitVal);

            if(!unitVal){
                fillSelect($dir, [], "— مدیر ندارد —", null);
                fillSelect($chief, [], "— رئیس ندارد —", null);
                fillSelect($role, [], "— انتخاب کنید —", null);
                fillSelect($title, [], "— انتخاب کنید —", null);
                return;
            }

            // --- مدیر / رئیس
            var urlManagers =
                window.location.origin +
                "/admin/reports/get_managers/?unit_id=" + unitVal +
                (empID ? "&employee_id=" + empID : "");

            fetchJSON(urlManagers).done(function(resp){

                var list = resp.results || [];
                var managers = list.filter(x => x.role_code === "900" || x.role_code === "901");
                var chiefs   = list.filter(x => x.role_code === "902");

                var dirSel   = firstLoad ? initDir   : null;
                var chiefSel = firstLoad ? initChief : null;
                var mgrSel   = firstLoad ? initMgr   : null;

                fillSelect($dir, managers, managers.length ? null : "— مدیر ندارد —", dirSel);
                fillSelect($chief, chiefs,   chiefs.length ? null : "— رئیس ندارد —", chiefSel);

                if($mgr.length){
                    fillSelect($mgr, managers, managers.length ? null : "— مدیر ندارد —", mgrSel);
                }
            });

            // --- نقش / عنوان شغلی
            var urlRoles =
                window.location.origin +
                "/admin/reports/get_jobroles/?unit_id=" + unitVal;

            fetchJSON(urlRoles).done(function(resp){

                var roles  = resp.roles  || [];
                var titles = resp.titles || [];

                var roleSel  = firstLoad ? initRole  : null;
                var titleSel = firstLoad ? initTitle : null;

                fillSelect($role,  roles,  "— انتخاب کنید —", roleSel);
                if (!firstLoad) {
                    $title.val("");
                }
                fillSelect($title, titles, "— انتخاب کنید —", titleSel);
            });
            firstLoad = false;
        }

        // ---------------------------------------------------
        // 🔵 Event ها
        // ---------------------------------------------------

        $(document).on("change", "#id_organization", reloadUnits);
        $(document).on("select2:select", "#id_organization", reloadUnits);

        $(document).on("change", "#id_unit", reloadDropdowns);
        $(document).on("select2:select", "#id_unit", reloadDropdowns);

        // لود اولیه
        reloadDropdowns();
    }

    $(init);

})(django.jQuery);
